#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Neural network classifiers."""

__author__ = 'Marco Fossati'
__email__ = 'fossati@spaziodati.eu'
__version__ = '1.0'
__license__ = 'GPL-3.0'
__copyright__ = 'Copyleft 2019, Hjfocs'

import logging
import os
from contextlib import redirect_stderr

from recordlinkage.adapters import KerasAdapter
from recordlinkage.base import BaseClassifier

from soweego.commons import constants

with redirect_stderr(open(os.devnull, "w")):
    # When the keras module is initialized it will print a message to `stderr`
    # saying which backend it is using. To avoid this behavior we
    # redirect stderr to `devnull` for the statements in this block.
    from keras.callbacks import EarlyStopping, ModelCheckpoint, TensorBoard
    from keras.layers import BatchNormalization, Dense, Dropout
    from keras.models import Sequential


LOGGER = logging.getLogger(__name__)


class _BaseNN(KerasAdapter, BaseClassifier):
    """
    This class implements the fit method, which is common to all
    NN implementations.
    """

    def _fit(self, features, answers,
             batch_size=constants.BATCH_SIZE,
             epochs=constants.EPOCHS,
             validation_split=constants.VALIDATION_SPLIT
             ):
        history = self.kernel.fit(
            x=features,
            y=answers,
            validation_split=validation_split,
            batch_size=batch_size,
            epochs=epochs,
            callbacks=[
                EarlyStopping(monitor='val_loss', patience=100,
                              verbose=2, restore_best_weights=True),
                ModelCheckpoint(
                    os.path.join(
                        constants.SHARED_FOLDER,
                        constants.NEURAL_NETWORK_CHECKPOINT_MODEL % self.__class__.__name__
                    ),
                    save_best_only=True
                ),
                TensorBoard(log_dir=constants.SHARED_FOLDER)
            ]
        )
        LOGGER.info('Fit parameters: %s', history.params)

    def __repr__(self):
        return f'{self.__class__.__name__}(optimizer={self.kernel.optimizer.__class__.__name__}, loss={self.kernel.loss}, metrics={self.kernel.metrics}, config={self.kernel.get_config()})'


class SingleLayerPerceptron(_BaseNN):
    """A single-layer perceptron classifier."""

    def __init__(self, input_dim, **kwargs):
        super(SingleLayerPerceptron, self).__init__()

        model = Sequential()
        model.add(
            Dense(1, input_dim=input_dim, activation=constants.ACTIVATION))
        model.compile(
            optimizer=kwargs.get('optimizer', constants.OPTIMIZER),
            loss=constants.LOSS,
            metrics=constants.METRICS
        )

        self.kernel = model


class MultiLayerPerceptron(_BaseNN):
    """A multi-layer perceptron classifier."""

    def __init__(self, input_dimension):
        super(MultiLayerPerceptron, self).__init__()

        model = Sequential([
            Dense(128, input_dim=input_dimension, activation='relu'),
            BatchNormalization(),
            Dense(32, activation='relu'),
            BatchNormalization(),
            Dense(1, activation='sigmoid')

        ])

        model.compile(
            optimizer='adadelta',
            loss='binary_crossentropy',
            metrics=['accuracy']
        )

        self.kernel = model
