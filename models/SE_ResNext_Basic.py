import torch
import torch.nn as nn
import torch.nn.functional as F
from torchsummary import summary
from models.BasicModule import BasicModule
from IPython import embed


def activation(act_type='prelu'):
    if act_type == 'prelu':
        act = nn.PReLU()
    elif act_type == 'relu':
        act = nn.ReLU(inplace=True)
    else:
        raise NotImplementedError
    return act


class Block(nn.Module):
    '''Grouped convolution block.'''
    expansion = 2

    def __init__(self, in_planes, cardinality=32, bottleneck_width=4, stride=1):
        super(Block, self).__init__()
        group_width = cardinality * bottleneck_width
        self.conv1 = nn.Conv1d(in_planes, group_width, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm1d(group_width)
        self.conv2 = nn.Conv1d(group_width, group_width, kernel_size=3, stride=stride, padding=1, groups=cardinality, bias=False)
        self.bn2 = nn.BatchNorm1d(group_width)
        self.conv3 = nn.Conv1d(group_width, self.expansion*group_width, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm1d(self.expansion*group_width)
        self.relu = nn.ReLU(inplace=True)
        # self.dropout = nn.Dropout(.2)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != self.expansion*group_width:
            self.shortcut = nn.Sequential(
                nn.Conv1d(in_planes, self.expansion*group_width, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm1d(self.expansion*group_width)
            )
        self.globalAvgPool = nn.AdaptiveAvgPool1d(1)

        self.fc1 = nn.Conv1d(self.expansion*group_width, group_width, kernel_size=1)  # Use nn.Conv1d instead of nn.Linear
        self.fc2 = nn.Conv1d(group_width, self.expansion*group_width, kernel_size=1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):

        out = self.relu(self.bn1(self.conv1(x)))
        out = self.relu(self.bn2(self.conv2(out)))
        # out = self.dropout(out)
        out = self.bn3(self.conv3(out))

        original_out = out
        out = self.globalAvgPool(out)
        # out = out.view(out.size(0), -1)
        out = self.fc1(out)
        out = self.relu(out)
        out = self.fc2(out)
        out = self.sigmoid(out)
        # out = out.view(out.size(0),out.size(1),1,1)
        out = out * original_out


        out += self.shortcut(x)

        out = self.relu(out)
        return out


class SEResNeXt(BasicModule):
    def __init__(self, num_blocks, cardinality, bottleneck_width, num_classes=55):
        super(SEResNeXt, self).__init__()
        self.cardinality = cardinality
        self.bottleneck_width = bottleneck_width
        self.in_planes = 64

        self.conv1 = nn.Conv1d(8, 64, kernel_size=15, stride=2, padding=7, bias=False)
        self.bn1 = nn.BatchNorm1d(64)
        self.relu = nn.ReLU(inplace=True)
        self.layer1 = self._make_layer(num_blocks[0], 1)
        self.layer2 = self._make_layer(num_blocks[1], 2)
        self.layer3 = self._make_layer(num_blocks[2], 2)
        self.layer4 = self._make_layer(num_blocks[3], 2)
        self.maxpool = nn.MaxPool1d(kernel_size=3, stride=2, padding=1)
        self.avgpool = nn.AdaptiveAvgPool1d(1)
        self.linear = nn.Linear(16 * cardinality * bottleneck_width, num_classes)
        self.sigmoid = nn.Sigmoid()

        self.init()

    def _make_layer(self, num_blocks, stride):
        strides = [stride] + [1]*(num_blocks-1)
        layers = []
        for stride in strides:
            layers.append(Block(self.in_planes, self.cardinality, self.bottleneck_width, stride))
            self.in_planes = Block.expansion * self.cardinality * self.bottleneck_width
        # Increase bottleneck_width by 2 after each stage.
        self.bottleneck_width *= 2
        return nn.Sequential(*layers)

    def forward(self, data):
        out = self.relu(self.bn1(self.conv1(data)))
        out = self.maxpool(out)

        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.layer4(out)

        out = self.avgpool(out)
        out = out.view(out.size(0), -1)

        out = self.linear(out)
        out = self.sigmoid(out)
        return out


def SE_ResNeXt50_b_2x16d(num_classes=55):
    return SEResNeXt(num_blocks=[3, 4, 6, 3], cardinality=2, bottleneck_width=16, num_classes=num_classes)


def SE_ResNeXt50_b_2x32d(num_classes=55):
    return SEResNeXt(num_blocks=[3, 4, 6, 3], cardinality=2, bottleneck_width=32, num_classes=num_classes)


def SE_ResNeXt50_b_2x64d(num_classes=55):
    return SEResNeXt(num_blocks=[3, 4, 6, 3], cardinality=2, bottleneck_width=64, num_classes=num_classes)


def SE_ResNeXt50_b_4x64d(num_classes=55):
    return SEResNeXt(num_blocks=[3, 4, 6, 3], cardinality=4, bottleneck_width=64, num_classes=num_classes)


def SE_ResNeXt101_b_2x64d(num_classes=55):
    return SEResNeXt(num_blocks=[3, 4, 23, 3], cardinality=2, bottleneck_width=64, num_classes=num_classes)


def SE_ResNeXt101_b_4x64d(num_classes=55):
    return SEResNeXt(num_blocks=[3, 4, 23, 3], cardinality=4, bottleneck_width=64, num_classes=num_classes)


def ResNeXt152_b_2x64d(num_classes=55):
    return SEResNeXt(num_blocks=[3, 8, 36, 3], cardinality=2, bottleneck_width=64, num_classes=num_classes)


def SE_ResNeXt152_b_4x64d(num_classes=55):
    return SEResNeXt(num_blocks=[3, 8, 36, 3], cardinality=4, bottleneck_width=64, num_classes=num_classes)


def test_ResNeXt():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = SE_ResNeXt101_b_4x64d(num_classes=55)
    model = net.to(device)
    print( summary(net, input_size=(8, 5000)) )


if __name__ == '__main__':
    test_ResNeXt()
