#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Constants"""

__author__ = 'Marco Fossati'
__email__ = 'fossati@spaziodati.eu'
__version__ = '1.0'
__license__ = 'GPL-3.0'
__copyright__ = 'Copyleft 2018, Hjfocs'

from typing import TypeVar

from recordlinkage import NaiveBayesClassifier, SVMClassifier

from soweego.importer import models
from soweego.wikidata import vocabulary

# Miscellanea
LAST_MODIFIED = 'last-modified'

PROD_DB = 'PROD_DB'
TEST_DB = 'TEST_DB'

DB_ENGINE = 'DB_ENGINE'
USER = 'USER'
PASSWORD = 'PASSWORD'
HOST = 'HOST'

IDENTIFIER = 'identifier'
LINKS = 'links'
DATASET = 'dataset'
METADATA = 'metadata'

# SPARQL queries
CLASS = 'class'
OCCUPATION = 'occupation'
SUPPORTED_QUERY_TYPES = (CLASS, OCCUPATION)
SUPPORTED_QUERY_SELECTORS = (IDENTIFIER, LINKS, DATASET, METADATA)

# Entity types and corresponding Wikidata query
HANDLED_ENTITIES = {
    'band': CLASS,
    'musician': OCCUPATION,
    'actor': OCCUPATION,
    'director': OCCUPATION,
    'producer': OCCUPATION
}

# DB entity Python types for typed function signatures
DB_ENTITY = TypeVar('DB_ENTITY', models.base_entity.BaseEntity,
                    models.base_link_entity.BaseLinkEntity, models.base_nlp_entity.BaseNlpEntity)

# TODO add IMDb entities
# DB entities and their Wikidata class QID
TARGET_CATALOGS = {
    'discogs': {
        'musician': {
            'qid': vocabulary.MUSICIAN,
            'entity': models.discogs_entity.DiscogsMusicianEntity,
            'link_entity': models.discogs_entity.DiscogsMusicianLinkEntity,
            'nlp_entity': models.discogs_entity.DiscogsMusicianNlpEntity
        },
        'band': {
            'qid': vocabulary.BAND,
            'entity': models.discogs_entity.DiscogsGroupEntity,
            'link_entity': models.discogs_entity.DiscogsGroupLinkEntity,
            'nlp_entity': models.discogs_entity.DiscogsGroupNlpEntity
        }
    },
    'imdb': {
        'actor': {
            'qid': vocabulary.ACTOR,
            'entity': None,
            'link_entity': None,
            'nlp_entity': None
        },
        'director': {
            'qid': vocabulary.FILM_DIRECTOR,
            'entity': None,
            'link_entity': None,
            'nlp_entity': None
        },
        'producer': {
            'qid': vocabulary.FILM_PRODUCER,
            'entity': None,
            'link_entity': None,
            'nlp_entity': None
        }
    },
    'musicbrainz': {
        'musician': {
            'qid': vocabulary.MUSICIAN,
            'entity': models.musicbrainz_entity.MusicbrainzArtistEntity,
            'link_entity': models.musicbrainz_entity.MusicbrainzArtistLinkEntity,
            'nlp_entity': None
        },
        'band': {
            'qid': vocabulary.BAND,
            'entity': models.musicbrainz_entity.MusicbrainzBandEntity,
            'link_entity': models.musicbrainz_entity.MusicbrainzBandLinkEntity,
            'nlp_entity': None
        }
    }
}

# Wikidata & target field names
QID = 'qid'
TID = 'tid'
ALIAS = 'alias'
PSEUDONYM = 'pseudonym'
DATE_OF_BIRTH = vocabulary.LINKER_PIDS[vocabulary.DATE_OF_BIRTH]
DATE_OF_DEATH = vocabulary.LINKER_PIDS[vocabulary.DATE_OF_DEATH]
# Consistent with BaseEntity
NAME = 'name'
NAME_TOKENS = 'name_tokens'
BIRTH_PRECISION = 'born_precision'
DEATH_PRECISION = 'died_precision'
# Consistent with BaseLinkEntity
URL = 'url'
URL_TOKENS = 'url_tokens'
# Consistent with BaseNlpEntity
DESCRIPTION = 'description'
DESCRIPTION_TOKENS = 'description_tokens'

# File names
WD_TRAINING_SET = 'wikidata_%s_training_set.jsonl.gz'
WD_CLASSIFICATION_SET = 'wikidata_%s_dataset.jsonl.gz'
WD_TRAINING_DATAFRAME = 'wikidata_%s_training_dataframe.pkl.gz'
WD_CLASSIFICATION_DATAFRAME = 'wikidata_%s_classification_dataframe.pkl.gz'
TARGET_TRAINING_SET = '%s_training_set.jsonl.gz'
TARGET_CLASSIFICATION_SET = '%s_dataset.jsonl.gz'
TARGET_TRAINING_DATAFRAME = '%s_training_dataframe.pkl.gz'
TARGET_CLASSIFICATION_DATAFRAME = '%s_classification_dataframe.pkl.gz'
TRAINING_SAMPLES = '%s_training_samples.pkl.gz'
LINKER_MODEL = '%s_%s_model.pkl'
LINKER_RESULT = '%s_linker_result.csv.gz'
LINKER_EVALUATION_PREDICTIONS = '%s_%s_linker_evaluation_predictions.csv.gz'
LINKER_PERFORMANCE = '%s_%s_linker_performance.txt'

# Supervised classification
CLASSIFIERS = {
    'naive_bayes': NaiveBayesClassifier,
    'support_vector_machines': SVMClassifier,
    'nb': NaiveBayesClassifier,  # Shorthand
    'svm': SVMClassifier  # Shorthand
}
CLASSIFICATION_RETURN_SERIES = ('classification.return_type', 'series')
CONFIDENCE_THRESHOLD = 0.5
