import os

import lasagne

from protfun.layers import MoleculeMapLayer
from protfun.models.protein_predictor import ProteinPredictor
from protfun.preprocess.data_prep import DataSetup
from protfun.visualizer.molview import MoleculeView

grid_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../data/computed_grid.npy")


def visualize():
    for i in range(108, 182):
        dummy = lasagne.layers.InputLayer(shape=(None,))
        preprocess = MoleculeMapLayer(incoming=dummy, minibatch_size=1)
        grids = preprocess.get_output_for(molecule_ids=[i]).eval()
        viewer = MoleculeView(data={"potential": grids[0, 0], "density": grids[0, 1]}, info={"name": "test"})
        viewer.density3d()
        viewer.potential3d()


def collect_proteins():
    path_to_enz = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../data/enzymes/3.4.21.labels")
    with open(path_to_enz, 'r') as f:
        enzymes = [e.strip() for e in f.readlines()[:500]]
    path_to_enz = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../data/enzymes/3.4.24.labels")
    with open(path_to_enz, 'r') as f:
        enzymes += [e.strip() for e in f.readlines()[:500]]
    return enzymes


def train_enzymes():
    enzymes = collect_proteins()

    data = DataSetup(prot_codes=enzymes,
                     download_again=False,
                     process_again=False)

    train_test_data = data.load_dataset()

    predictor = ProteinPredictor(data=train_test_data,
                                 minibatch_size=1)

    predictor.train(epoch_count=100)
    predictor.test()
    predictor.summarize()


if __name__ == "__main__":
    train_enzymes()
    # visualize()
