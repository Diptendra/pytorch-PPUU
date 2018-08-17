import argparse
import numpy
import gym

parser = argparse.ArgumentParser()
parser.add_argument('-seed', type=int, default=0)
parser.add_argument('-nb_conditions', type=int, default=10)
parser.add_argument('-nb_samples', type=int, default=1)
parser.add_argument('-display', type=int, default=1)
parser.add_argument('-map', type=str, default='i80', choices={'i80', 'us101', 'lanker', 'peach'})

opt = parser.parse_args()

kwargs = {
    'fps': 50,
    'nb_states': opt.nb_conditions,
    'display': opt.display
}

gym.envs.registration.register(
    id='I-80-v1',
    entry_point='map_i80_ctrl:ControlledI80',
    kwargs=kwargs,
)

env_names = {
    'i80': 'I-80-v1',
}

print('Building the environment (loading data, if any)')
env = gym.make(env_names[opt.map])

for episode in range(1000):
    env.reset()

    done = False
    while not done:
        observation, reward, done, info = env.step(numpy.zeros((2,)))
        # print(observation, reward, done, info)
        env.render()

    print('Episode completed!')

print('Done')
