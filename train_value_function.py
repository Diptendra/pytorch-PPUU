import torch, numpy, argparse, pdb, os, math, time, copy
import utils
import models
from dataloader import DataLoader
from torch.autograd import Variable
import torch.nn.functional as F
import torch.optim as optim


###########################################
# Train an imitation learner model
###########################################

parser = argparse.ArgumentParser()
# data params
parser.add_argument('-dataset', type=str, default='i80')
parser.add_argument('-v', type=int, default=4)
parser.add_argument('-model', type=str, default='policy-cnn-mdn')
parser.add_argument('-layers', type=int, default=3)
parser.add_argument('-fmap_geom', type=int, default=1)
parser.add_argument('-data_dir', type=str, default='/misc/vlgscratch4/LecunGroup/nvidia-collab/data/')
parser.add_argument('-model_dir', type=str, default='/misc/vlgscratch4/LecunGroup/nvidia-collab/models_v8/value_functions3/')
parser.add_argument('-n_episodes', type=int, default=20)
parser.add_argument('-lanes', type=int, default=8)
parser.add_argument('-ncond', type=int, default=20)
parser.add_argument('-npred', type=int, default=200)
parser.add_argument('-seed', type=int, default=1)
parser.add_argument('-batch_size', type=int, default=64)
parser.add_argument('-gamma', type=float, default=0.99)
parser.add_argument('-dropout', type=float, default=0.0)
parser.add_argument('-nfeature', type=int, default=128)
parser.add_argument('-n_hidden', type=int, default=128)
parser.add_argument('-lrt', type=float, default=0.0001)
parser.add_argument('-epoch_size', type=int, default=2000)
parser.add_argument('-nsync', type=int, default=1)
parser.add_argument('-combine', type=str, default='add')
parser.add_argument('-grad_clip', type=float, default=10)
parser.add_argument('-debug', type=int, default=0)
opt = parser.parse_args()


opt.n_actions = 2
opt.n_inputs = opt.ncond
opt.height = 117
opt.width = 24
opt.h_height = 14
opt.h_width = 3
opt.hidden_size = opt.nfeature*opt.h_height*opt.h_width



os.system('mkdir -p ' + opt.model_dir)

dataloader = DataLoader(None, opt, opt.dataset)

opt.model_file = f'{opt.model_dir}/model=value-bsize={opt.batch_size}-ncond={opt.ncond}-npred={opt.npred}-lrt={opt.lrt}-nhidden={opt.n_hidden}-nfeature={opt.nfeature}-gclip={opt.grad_clip}-dropout={opt.dropout}-gamma={opt.gamma}-nsync={opt.nsync}'

print(f'[will save model as: {opt.model_file}]')


model = models.ValueFunction(opt)
model.intype('gpu')
model_ = copy.deepcopy(model)

optimizer = optim.Adam(model.parameters(), opt.lrt)


gamma_mask = Variable(torch.from_numpy(numpy.array([opt.gamma**t for t in range(opt.npred + 1)])).float().cuda()).unsqueeze(0).expand(opt.batch_size, opt.npred + 1)


def train(nbatches):
    model.train()
    total_loss, nb = 0, 0
    for i in range(nbatches):
        optimizer.zero_grad()
        inputs, actions, targets, ids, sizes = dataloader.get_batch_fm('train')
        inputs = utils.make_variables(inputs)
        targets = utils.make_variables(targets)
        actions = Variable(actions)
        v = model(inputs[0], inputs[1])        
        if opt.nsync == 1:
            v_ = model(targets[0][:, -opt.ncond:], targets[1][:, -opt.ncond:])
        else:
            v_ = model_(targets[0][:, -opt.ncond:], targets[1][:, -opt.ncond:])
        images, states, _ = targets
        cost, _ = utils.proximity_cost(targets[0], targets[1], sizes, unnormalize=True, s_mean=dataloader.s_mean, s_std=dataloader.s_std)
        v_target = torch.sum(torch.cat((cost, v_), 1) * gamma_mask, 1).view(-1, 1)
        loss = F.mse_loss(v, Variable(v_target.data))
        if not math.isnan(loss.item()):
            loss.backward()
            if opt.grad_clip != -1:
                torch.nn.utils.clip_grad_norm_(model.parameters(), opt.grad_clip)
            optimizer.step()
            total_loss += loss.item()
            nb += 1
        else:
            print('warning, NaN')
    return total_loss / nb


def test(nbatches):
    model.eval()
    total_loss, nb = 0, 0
    for i in range(nbatches):
        optimizer.zero_grad()
        inputs, actions, targets, ids, sizes = dataloader.get_batch_fm('valid')
        inputs = utils.make_variables(inputs)
        targets = utils.make_variables(targets)
        actions = Variable(actions)
        v = model(inputs[0], inputs[1])
        if opt.nsync == 1:
            v_ = model(targets[0][:, -opt.ncond:], targets[1][:, -opt.ncond:])
        else:
            v_ = model_(targets[0][:, -opt.ncond:], targets[1][:, -opt.ncond:])
#        v_ = model_(targets[0][:, -opt.ncond:], targets[1][:, -opt.ncond:])
        images, states, _ = targets
        cost, _ = utils.proximity_cost(targets[0], targets[1], sizes, unnormalize=True, s_mean=dataloader.s_mean, s_std=dataloader.s_std)
#        cost = targets[2][:, :, 0]
        v_target = torch.sum(torch.cat((cost, v_), 1) * gamma_mask, 1).view(-1, 1)
        loss = F.mse_loss(v, Variable(v_target.data))
        if not math.isnan(loss.item()):
            total_loss += loss.item()
            nb += 1
        else:
            print('warning, NaN')
    return total_loss / nb






print('[training]')
best_valid_loss = 1e6
for i in range(100):
    train_loss = train(opt.epoch_size)
    valid_loss = test(opt.epoch_size)
    
    if opt.nsync == 1:
        if valid_loss < best_valid_loss:
            best_valid_loss = valid_loss
            model.intype('cpu')
            torch.save(model, opt.model_file + '.model')
            model.intype('gpu')
    else:
        model.intype('cpu')
        torch.save(model, opt.model_file + '.model')
        model.intype('gpu')

    log_string = f'iter {opt.epoch_size*i} | train loss: {train_loss:.5f}, valid: {valid_loss:.5f}, best valid loss: {best_valid_loss:.5f}'
    print(log_string)
    utils.log(opt.model_file + '.log', log_string)
    if opt.nsync > 1 and i % opt.nsync == 0:
        print('[updating target network]')
        utils.log(opt.model_file + '.log', '[updating target network]')
        model_ = copy.deepcopy(model)
