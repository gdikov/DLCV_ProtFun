import numpy as np
import theano
import theano.tensor as T
import lasagne
import colorlog as log
import logging

from protfun.layers.molmap_layer import MoleculeMapLayer
from protfun.layers.grid_rotate_layer import GridRotationLayer

log.basicConfig(level=logging.DEBUG)
floatX = theano.config.floatX
intX = np.int32


class DisjointClassModel(object):
    def __init__(self, name, n_classes):
        self.name = name
        self.n_classes = n_classes
        self.train_function = None
        self.validation_function = None
        self.output_layers = None

    def define_forward_pass(self, input_vars, output_layer):
        train_params = lasagne.layers.get_all_params(output_layer, trainable=True)
        targets = T.imatrix('targets')

        # define objective and training parameters
        train_predictions = lasagne.layers.get_output(output_layer)
        train_losses = T.mean(lasagne.objectives.binary_crossentropy(train_predictions, targets), axis=0)
        train_accuracies = T.mean(T.eq(train_predictions > 0.5, targets), axis=0, dtype=theano.config.floatX)

        val_predictions = lasagne.layers.get_output(output_layer, deterministic=True)
        val_losses = T.mean(lasagne.objectives.binary_crossentropy(val_predictions, targets), axis=0)
        val_accuracies = T.mean(T.eq(val_predictions > 0.5, targets), axis=0, dtype=theano.config.floatX)

        total_loss = T.mean(train_losses)

        train_params_updates = lasagne.updates.adam(loss_or_grads=total_loss,
                                                    params=train_params,
                                                    learning_rate=1e-4)

        self.train_function = theano.function(inputs=input_vars + [targets],
                                              outputs={'losses': train_losses, 'accs': train_accuracies,
                                                       'predictions': T.stack(train_predictions)},
                                              updates=train_params_updates)  # , profile=True)

        self.validation_function = theano.function(inputs=input_vars + [targets],
                                                   outputs={'losses': val_losses, 'accs': val_accuracies,
                                                            'predictions': T.stack(val_predictions)})
        log.info("Computational graph compiled")

    def get_output_layers(self):
        return self.output_layers

    def get_name(self):
        return self.name


class MemmapsDisjointClassifier(DisjointClassModel):
    def __init__(self, name, n_classes, network, minibatch_size):
        super(MemmapsDisjointClassifier, self).__init__(name, n_classes)
        self.minibatch_size = minibatch_size

        coords = T.tensor3('coords')
        charges = T.matrix('charges')
        vdwradii = T.matrix('vdwradii')
        n_atoms = T.ivector('n_atoms')
        coords_input = lasagne.layers.InputLayer(shape=(self.minibatch_size, None, None),
                                                 input_var=coords)
        charges_input = lasagne.layers.InputLayer(shape=(self.minibatch_size, None),
                                                  input_var=charges)
        vdwradii_input = lasagne.layers.InputLayer(shape=(self.minibatch_size, None),
                                                   input_var=vdwradii)
        natoms_input = lasagne.layers.InputLayer(shape=(self.minibatch_size,),
                                                 input_var=n_atoms)
        grids = MoleculeMapLayer(incomings=[coords_input, charges_input, vdwradii_input, natoms_input],
                                 minibatch_size=self.minibatch_size,
                                 use_esp=False)

        # apply the network to the preprocessed input
        self.output_layer = network(grids, n_outputs=n_classes)
        self.define_forward_pass(input_vars=[coords, charges, vdwradii, n_atoms], output_layer=self.output_layer)


class GridsDisjointClassifier(DisjointClassModel):
    def __init__(self, name, n_classes, network, grid_size, minibatch_size):
        super(GridsDisjointClassifier, self).__init__(name, n_classes)

        self.minibatch_size = minibatch_size
        grids = T.TensorType(floatX, (False,) * 5)()
        input_layer = lasagne.layers.InputLayer(shape=(self.minibatch_size, 2, grid_size, grid_size, grid_size),
                                                input_var=grids)
        rotated_grids = GridRotationLayer(incoming=input_layer, grid_side=grid_size)

        # apply the network to the preprocessed input
        self.output_layer = network(rotated_grids, n_outputs=n_classes)
        self.define_forward_pass(input_vars=[grids], output_layer=self.output_layer)
