#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Evaluation of supervised linking algorithms."""

__author__ = 'Marco Fossati'
__email__ = 'fossati@spaziodati.eu'
__version__ = '1.0'
__license__ = 'GPL-3.0'
__copyright__ = 'Copyleft 2019, Hjfocs'

import json
import logging
import os
import sys
from collections import defaultdict

import click
import recordlinkage as rl
from keras import backend as K
from numpy import mean, std
from pandas import concat
from sklearn.externals import joblib
from sklearn.model_selection import (
    GridSearchCV,
    StratifiedKFold,
    train_test_split,
)

from soweego.commons import constants, keys, target_database, utils
from soweego.linker import train, workflow

LOGGER = logging.getLogger(__name__)


# Let the user pass extra kwargs to the classifier
# This is for development purposes only, and is not explicitly documented
@click.command(
    context_settings={'ignore_unknown_options': True, 'allow_extra_args': True}
)
@click.argument('classifier', type=click.Choice(constants.CLASSIFIERS))
@click.argument(
    'catalog', type=click.Choice(target_database.supported_targets())
)
@click.argument(
    'entity', type=click.Choice(target_database.supported_entities())
)
@click.option('-k', '--k-folds', default=5, help="Number of folds, default: 5.")
@click.option(
    '-s',
    '--single',
    is_flag=True,
    help='Compute a single evaluation over all k folds, instead of k '
         'evaluations.',
)
@click.option(
    '-n',
    '--nested',
    is_flag=True,
    help='Compute a nested cross-validation with hyperparameters tuning via '
         'grid search. WARNING: this will take a lot of time.',
)
@click.option(
    '-m',
    '--metric',
    type=click.Choice(constants.PERFORMANCE_METRICS),
    default='f1',
    help="Performance metric for nested cross-validation. "
         "Use with '--nested'. Default: f1.",
)
@click.option(
    '-d',
    '--dir-io',
    type=click.Path(file_okay=False),
    default=constants.SHARED_FOLDER,
    help=f'Input/output directory, default: {constants.SHARED_FOLDER}.',
)
@click.pass_context
def cli(ctx, classifier, catalog, entity, k_folds, single, nested, metric,
        dir_io):
    """Evaluate the performance of a supervised linker.

    By default, run 5-fold cross-validation and
    return averaged performance scores.
    """
    kwargs = utils.handle_extra_cli_args(ctx.args)
    if kwargs is None:
        sys.exit(1)

    rl.set_option(*constants.CLASSIFICATION_RETURN_INDEX)

    performance_out, predictions_out = _build_output_paths(catalog, entity,
                                                           classifier, dir_io)

    # -n, --nested
    if nested:
        _run_nested(classifier, catalog, entity, k_folds, metric, kwargs,
                    performance_out, dir_io)
        sys.exit(0)

    # -s, --single
    if single:
        _run_single(classifier, catalog, entity, k_folds, kwargs,
                    performance_out, predictions_out, dir_io)
        sys.exit(0)

    # Default: average evaluation over k-fold
    _run_average(classifier, catalog, entity, k_folds, kwargs, performance_out,
                 predictions_out, dir_io)


def _build_output_paths(catalog, entity, classifier, dir_io):
    performance_outpath = os.path.join(
        dir_io,
        constants.LINKER_PERFORMANCE.format(catalog, entity, classifier)
    )
    predictions_outpath = os.path.join(
        dir_io,
        constants.LINKER_EVALUATION_PREDICTIONS.format(
            catalog, entity, classifier
        ),
    )
    os.makedirs(os.path.dirname(predictions_outpath), exist_ok=True)

    return performance_outpath, predictions_outpath


def _run_average(classifier, catalog, entity, k_folds, kwargs, performance_out,
                 predictions_out, dir_io):
    LOGGER.info('Starting average evaluation over %d folds ...', k_folds)

    predictions, p_mean, p_std, r_mean, r_std, fscore_mean, fscore_std = average_k_fold(
        constants.CLASSIFIERS[classifier],
        catalog,
        entity,
        k_folds,
        dir_io,
        **kwargs,
    )

    LOGGER.info(
        'Evaluation done. '
        'Precision: mean = %s; std = %s; '
        'recall: mean = %s; std = %s; '
        'F-score: mean = %s; std = %s',
        p_mean,
        p_std,
        r_mean,
        r_std,
        fscore_mean,
        fscore_std,
    )

    predictions.to_series().to_csv(predictions_out, header=False)
    with open(performance_out, 'w') as out:
        out.write(
            f'Precision:\n'
            f'\tmean = {p_mean}\n'
            f'\tstandard deviation = {p_std}\n'
            f'Recall:\n'
            f'\tmean = {r_mean}\n'
            f'\tstandard deviation = {r_std}\n'
            f'F-score:\n'
            f'\tmean = {fscore_mean}\n'
            f'\tstandard deviation = {fscore_std}\n'
        )

    LOGGER.info(
        "Predictions dumped to '%s', performance dumped to '%s'",
        predictions_out,
        performance_out,
    )


def _run_single(classifier, catalog, entity, k_folds, kwargs, performance_out,
                predictions_out, dir_io):
    LOGGER.info('Starting single evaluation over %d folds ...', k_folds)

    predictions, (
        precision,
        recall,
        fscore,
        confusion_matrix,
    ) = single_k_fold(
        constants.CLASSIFIERS[classifier],
        catalog,
        entity,
        k_folds,
        dir_io,
        **kwargs,
    )

    LOGGER.info(
        'Evaluation done. '
        'Precision: %s; '
        'recall: %s; '
        'F-score: %s',
        precision, recall, fscore
    )

    predictions.to_series().to_csv(predictions_out, header=False)
    with open(performance_out, 'w') as out:
        out.write(
            f'Precision: {precision}\n'
            f'Recall: {recall}\n'
            f'F-score: {fscore}\n'
            f'Confusion matrix:\n{confusion_matrix}\n'
        )

    LOGGER.info(
        "Predictions dumped to '%s', Performance dumped to '%s'",
        predictions_out,
        performance_out,
    )


def _run_nested(classifier, catalog, entity, k_folds, metric, kwargs,
                performance_out, dir_io):
    LOGGER.warning(
        'You have opted for the slowest evaluation option, '
        'please be patient ...'
    )
    LOGGER.info(
        f'Starting nested {k_folds}-fold cross-validation with '
        f'hyperparameters tuning via grid search ...',
    )

    clf = constants.CLASSIFIERS[classifier]
    param_grid = constants.PARAMETER_GRIDS[clf]

    result = nested_k_fold_with_grid_search(
        clf,
        param_grid,
        catalog,
        entity,
        k_folds,
        metric,
        dir_io,
        **kwargs,
    )

    LOGGER.info('Evaluation done: %s', result)

    # Persist best models
    for k, model in enumerate(result.pop('best_models'), 1):
        model_out = os.path.join(
            dir_io,
            constants.LINKER_NESTED_CV_BEST_MODEL.format(
                catalog, entity, classifier, k
            )
        )

        result['best_models'].append(model_out)
        joblib.dump(model, model_out)

        LOGGER.info(
            "Best model for fold %d dumped to '%s'", k, model_out
        )

    performance_out = performance_out.replace('txt', 'json')
    with open(performance_out, 'w') as out:
        json.dump(result, out, indent=2)

    LOGGER.info(
        "%s performance dumped to '%s'", metric, performance_out
    )


def _compute_performance(test_index, predictions, test_vectors_size):
    LOGGER.info('Running performance evaluation ...')

    confusion_matrix = rl.confusion_matrix(
        test_index, predictions, total=test_vectors_size
    )
    precision = rl.precision(test_index, predictions)
    recall = rl.recall(test_index, predictions)
    fscore = rl.fscore(confusion_matrix)

    LOGGER.info(
        'Precision: %f - Recall: %f - F-score: %f', precision, recall, fscore
    )
    LOGGER.info('Confusion matrix: %s', confusion_matrix)

    return precision, recall, fscore, confusion_matrix


def nested_k_fold_with_grid_search(
    classifier, param_grid, catalog, entity, k, scoring, dir_io, **kwargs
):
    if classifier in (
        keys.SINGLE_LAYER_PERCEPTRON,
        keys.MULTI_LAYER_PERCEPTRON,
    ):
        # TODO make Keras work with GridSearchCV
        raise NotImplementedError(
            f'Grid search for {classifier} is not supported'
        )

    result = defaultdict(list)

    dataset, positive_samples_index = train.build_dataset(
        'training', catalog, entity, dir_io
    )
    model = workflow.init_model(classifier, **kwargs).kernel

    inner_k_fold, target = utils.prepare_stratified_k_fold(
        k, dataset, positive_samples_index
    )
    outer_k_fold = StratifiedKFold(n_splits=k, shuffle=True, random_state=1269)
    grid_search = GridSearchCV(
        model,
        param_grid,
        scoring=scoring,
        n_jobs=-1,
        cv=inner_k_fold,
        verbose=2,
    )
    dataset = dataset.to_numpy()

    for train_index, test_index in outer_k_fold.split(dataset, target):
        # Run grid search
        grid_search.fit(dataset[train_index], target[train_index])
        # Grid search best score is the train score
        result[f'train_{scoring}'].append(grid_search.best_score_)
        # Let grid search compute the test score
        test_score = grid_search.score(dataset[test_index], target[test_index])
        result[f'test_{scoring}'].append(test_score)
        best_model = grid_search.best_estimator_
        result['best_models'].append(best_model)

    return result


def average_k_fold(classifier, catalog, entity, k, dir_io, **kwargs):
    predictions, precisions, recalls, fscores = None, [], [], []
    dataset, positive_samples_index = train.build_dataset(
        'training', catalog, entity, dir_io
    )
    k_fold, binary_target_variables = utils.prepare_stratified_k_fold(
        k, dataset, positive_samples_index
    )

    for train_index, test_index in k_fold.split(
        dataset, binary_target_variables
    ):
        training, test = dataset.iloc[train_index], dataset.iloc[test_index]

        model = utils.initialize_classifier(classifier, dataset, **kwargs)
        model.fit(training, positive_samples_index & training.index)

        preds = model.predict(test)
        K.clear_session()

        p, r, f, _ = _compute_performance(
            positive_samples_index & test.index, preds, len(test)
        )

        if predictions is None:
            predictions = preds
        else:
            predictions |= preds

        precisions.append(p)
        recalls.append(r)
        fscores.append(f)

    return (
        predictions,
        mean(precisions),
        std(precisions),
        mean(recalls),
        std(recalls),
        mean(fscores),
        std(fscores),
    )


def single_k_fold(classifier, catalog, entity, k, dir_io, **kwargs):
    predictions, test_set = None, []
    dataset, positive_samples_index = train.build_dataset(
        'training', catalog, entity, dir_io
    )
    k_fold, binary_target_variables = utils.prepare_stratified_k_fold(
        k, dataset, positive_samples_index
    )

    for train_index, test_index in k_fold.split(
        dataset, binary_target_variables
    ):

        training, test = dataset.iloc[train_index], dataset.iloc[test_index]
        test_set.append(test)

        model = workflow.init_model(classifier, **kwargs)
        model.fit(training, positive_samples_index & training.index)

        if predictions is None:
            predictions = model.predict(test)
        else:
            predictions |= model.predict(test)

    test_set = concat(test_set)
    return (
        predictions,
        _compute_performance(
            positive_samples_index & test_set.index, predictions, len(test_set)
        ),
    )


def random_split(wd_chunk, target_chunk):
    wd_train, wd_test = train_test_split(wd_chunk, test_size=0.33)
    target_train, target_test = train_test_split(target_chunk, test_size=0.33)
    return wd_train, target_train, wd_test, target_test
