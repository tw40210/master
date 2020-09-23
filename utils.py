import numpy as np
import scipy
import scipy.signal
import scipy.fftpack
import librosa
import argparse
import hparam
import matplotlib.pyplot as plt
from typing import Dict, List
import os
import torch
from tqdm import tqdm
from model import ResNet, BasicBlock, get_BCE_loss
import torch.nn as nn
from tensorboardX import SummaryWriter

device=torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def get_Resnet():
    model = ResNet(BasicBlock, [2, 2, 2, 2])
    num_fout = model.conv1.out_channels
    model.conv1 = nn.Conv2d(3, num_fout, kernel_size=(7, 7), stride=(2, 2), padding=(3, 3),
                            bias=False)
    model.fc = nn.Linear(model.fc.in_features, 6)
    model.avgpool = nn.AvgPool2d(kernel_size=(17, 1), stride=1, padding=0)

    return model


def whole_song_test(path, f_path, model=None, writer=None):
    if not model:
        model = get_Resnet()
    if not writer:
        writer= SummaryWriter()

    wav_files = [os.path.join(path, file) for file in os.listdir(path) if '.wav' in file]
    labels = [os.path.join(path, label) for label in os.listdir(path) if '.notes.' in label]
    features = [os.path.join(f_path, features) for features in os.listdir(f_path) if '_FEAT' in features]


    for index in range(len(features)):
        record=[]


        features_full = np.load(features[index])

        label_note = read_notefile(labels[index])
        label_note, label_pitch = note2timestep(label_note)
        label_note = np.array(label_note)
        label_pitch = np.array(label_pitch)

        # cut muted tail from feature
        features_full = features_full[:, :label_note.shape[0]]
        # pad 9 zero steps in both head and tail
        zero_pad = np.zeros((features_full.shape[0], 9))
        features_full = np.concatenate((zero_pad, features_full), axis=1)
        features_full = np.concatenate((features_full, zero_pad), axis=1)

        for test_step in tqdm(range(features_full.shape[1]-18)) :
            curr_clip = features_full[:, test_step:test_step+19]
            curr_clip = torch.from_numpy(curr_clip)
            curr_clip = curr_clip.view(3,522,-1).float()
            curr_clip = curr_clip.unsqueeze(0)
            curr_clip = curr_clip.to(device)
            model = model.to(device)
            out_label = model(curr_clip)
            out_label = out_label.squeeze(0).squeeze(0).cpu().detach().numpy()

            record.append(out_label)

        record = np.array(record)

        for la_idx in range(record.shape[1]):
            plt.title(f"{la_idx}")
            plt.ylim(0,1)
            plt.plot(record[:,la_idx])
            plt.show()
            writer.








def get_accuracy(est_label, ref_label):
    correct = 0
    total = ref_label.shape[0]*ref_label.shape[1]

    for batch_idx in range(ref_label.shape[0]):
        for frame_idx in range(ref_label.shape[1]):
            norm_sa = est_label[batch_idx][frame_idx][0]+est_label[batch_idx][frame_idx][1]
            norm_on = est_label[batch_idx][frame_idx][2]+est_label[batch_idx][frame_idx][3] # make sure the sum of on and Xon =1
            norm_off = est_label[batch_idx][frame_idx][4]+est_label[batch_idx][frame_idx][5]
            est_label[batch_idx][frame_idx][0]/=norm_sa
            est_label[batch_idx][frame_idx][1]/=norm_sa
            est_label[batch_idx][frame_idx][2]/=norm_on
            est_label[batch_idx][frame_idx][3]/=norm_on
            est_label[batch_idx][frame_idx][4]/=norm_off
            est_label[batch_idx][frame_idx][5]/=norm_off


    est_label = (est_label > hparam.label_threshold).int()
    ref_label = ref_label.int()

    for batch_idx in range(ref_label.shape[0]):
        for frame_idx in range(ref_label.shape[1]):
            if torch.equal(est_label[batch_idx][frame_idx], ref_label[batch_idx][frame_idx]):
                correct+=1

    print(est_label[0],"||",  ref_label[0])

    return correct/total




def read_notefile(path, limit_len=None):
    notes = []
    with open(path, 'r') as txt:
        lines = txt.readlines()
        lines = lines[1:]
        for line in lines:
            note = list(map(float, line.split(', ')))
            notes.append(note)

    return notes


def note2timestep(notes: List):
    timestep = []
    pitch=[]
    tail=0
    end_tail=0
    for idx, note in enumerate(notes):
        status = [1, 0, 0, 1, 0, 1]  # S, A, O, -O, X, -X
        while (len(timestep) < note[0] // 0.02):
            timestep.append(status)
            pitch.append(0)

        if idx > 0:
            if note[0]-end_tail<1e-4:
                timestep[-1] = [0, 1, 1, 0, 1, 0]
                pitch[-1]=(note[2])
            else:
                status = [0, 1, 1, 0, 0, 1]
                timestep.append(status)
                pitch.append(note[2])
        else:
            status = [0, 1, 1, 0, 0, 1]
            timestep.append(status)
            pitch.append(note[2])

        # tail = note[0] // 0.02 * 0.02 + 0.02
        tail=len(timestep)*0.02
        end_tail = (note[0]+note[1])// 0.02 * 0.02 + 0.02
        status = [0, 1, 0, 1, 0, 1]
        ccc = ((note[0] + note[1] - tail) / 0.02)
        for _ in range(int((note[0] + note[1] - tail+1e-4) // 0.02)):
            timestep.append(status)
            pitch.append(note[2])

        status = [0, 1, 0, 1, 1, 0]
        timestep.append(status)
        pitch.append(note[2])
        # print(len(timestep), len(pitch))

    return timestep, pitch


if __name__ == '__main__':
    path = "data/test_sample/wav_label"
    f_path = "data/test_sample/FEAT"

    whole_song_test(path, f_path)

    # for file in os.listdir('data/train/TONAS/Deblas/'):
    #     if '.notes.Corrected' in file:
    #         dir = f'data/train/TONAS/Deblas/{file}'
    #         notes = read_notefile(dir)
    #         aa,pp = note2timestep(notes)
    #
    #         print(((notes[-1][0]+notes[-1][1]+1e-4)//0.02+1)*0.02, len(aa)*0.02,file)
    #         assert ((notes[-1][0]+notes[-1][1]+1e-4)//0.02+1)*0.02==len(aa)*0.02
    #
    #         aa = np.array(aa)
    #         pp = np.array(pp)


    # dir = f'data/train/TONAS/Deblas/52-M1_ManueldeAngustias.notes.Corrected'
    # notes = read_notefile(dir)
    # aa,pp = note2timestep(notes)
    # aa = np.array(aa)
    # pp = np.array(pp)