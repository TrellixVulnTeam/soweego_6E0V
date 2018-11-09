#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Validation of Wikidata statements against a target catalog"""

__author__ = 'Marco Fossati'
__email__ = 'fossati@spaziodati.eu'
__version__ = '1.0'
__license__ = 'GPL-3.0'
__copyright__ = 'Copyleft 2018, Hjfocs'

import json
import logging
import re
from collections import defaultdict

import click
import regex
from sqlalchemy import or_

from soweego.commons import url_utils
from soweego.commons.constants import HANDLED_ENTITIES, TARGET_CATALOGS
from soweego.commons.db_manager import DBManager
from soweego.importer.models.base_entity import BaseEntity
from soweego.importer.models.musicbrainz_entity import (MusicbrainzBandEntity,
                                                        MusicbrainzPersonEntity)
from soweego.ingestor import wikidata_bot
from soweego.wikidata import api_requests, sparql_queries, vocabulary

LOGGER = logging.getLogger(__name__)


@click.command()
@click.argument('wikidata_query', type=click.Choice(['class', 'occupation']))
@click.argument('class_qid')
@click.argument('catalog_pid')
@click.argument('database_table')
@click.option('-o', '--outfile', type=click.File('w'), default='output/non_existent_ids.json', help="default: 'output/non_existent_ids.json'")
def check_existence_cli(wikidata_query, class_qid, catalog_pid, database_table, outfile):
    """Check the existence of identifier statements.

    Dump a JSON file of invalid ones ``{identifier: QID}``
    """
    entity = BaseEntity
    if database_table == 'musicbrainz_person':
        entity = MusicbrainzPersonEntity
    elif database_table == 'musicbrainz_band':
        entity = MusicbrainzBandEntity
    else:
        LOGGER.error('Not able to retrive entity for given database_table')

    invalid = check_existence(wikidata_query, class_qid,
                              catalog_pid, entity)
    json.dump(invalid, outfile, indent=2)


def check_existence(class_or_occupation_query, class_qid, catalog_pid, entity: BaseEntity):
    query_type = 'identifier', class_or_occupation_query
    session = _connect_to_db()
    invalid = defaultdict(set)
    count = 0

    for result in sparql_queries.run_identifier_or_links_query(query_type, class_qid, catalog_pid, 0):
        for qid, target_id in result.items():
            results = session.query(entity).filter(
                entity.catalog_id == target_id).all()
            if not results:
                LOGGER.warning(
                    '%s identifier %s is invalid', qid, target_id)
                invalid[target_id].add(qid)
                count += 1

    LOGGER.info('Total invalid identifiers = %d', count)
    # Sets are not serializable to JSON, so cast them to lists
    return {target_id: list(qids) for target_id, qids in invalid.items()}


def _connect_to_db():
    db_manager = DBManager()
    session = db_manager.new_session()
    return session


@click.command()
@click.argument('entity', type=click.Choice(HANDLED_ENTITIES.keys()))
@click.argument('catalog', type=click.Choice(TARGET_CATALOGS.keys()))
@click.option('--wikidata-dump/--no-wikidata-dump', default=False, help='Dump links gathered from Wikidata')
@click.option('--upload/--no-upload', default=True, help='Upload check results to Wikidata')
@click.option('--sandbox/--no-sandbox', default=False, help='Upload to the Wikidata sandbox item Q4115189')
@click.option('-d', '--deprecated-outfile', type=click.File('w'), default='output/deprecated_ids.json', help="default: 'output/deprecated_ids.json'")
@click.option('-e', '--ext-ids-outfile', type=click.File('w'), default='output/external_ids_to_be_added.tsv', help="default: 'output/external_ids_to_be_added.tsv'")
@click.option('-u', '--urls-outfile', type=click.File('w'), default='output/urls_to_be_added.tsv', help="default: 'output/urls_to_be_added.tsv'")
@click.option('-w', '--wikidata-outfile', type=click.File('w'), default='output/wikidata_links.json', help="default: 'output/wikidata_links.json'")
def check_links_cli(entity, catalog, wikidata_dump, upload, sandbox, deprecated_outfile, ext_ids_outfile, urls_outfile, wikidata_outfile):
    """Check the validity of identifier statements based on the available links.

    Dump 3 files:
    - catalog identifiers to be deprecated, as a JSON ``{identifer: QID}``;
    - external identifiers to be added, as a TSV ``QID  identifier_PID  identifier``;
    - URLs to be added, as a TSV ``QID  P973   URL``.
    """
    to_deprecate, ext_ids_to_add, urls_to_add, wikidata = check_links(
        entity, catalog)

    if wikidata_dump:
        json.dump({qid: {data_type: list(values) for data_type, values in data.items()}
                   for qid, data in wikidata.items()}, wikidata_outfile, indent=2, ensure_ascii=False)
        LOGGER.info('Wikidata links dumped to %s', wikidata_outfile.name)
    if upload:
        upload_links(to_deprecate, ext_ids_to_add,
                     urls_to_add, catalog, sandbox)

    json.dump({target_id: list(qids) for target_id,
               qids in to_deprecate.items()}, deprecated_outfile, indent=2)
    ext_ids_outfile.writelines(
        ['\t'.join(triple) + '\n' for triple in ext_ids_to_add])
    urls_outfile.writelines(
        ['\t'.join(triple) + '\n' for triple in urls_to_add])
    LOGGER.info('Result dumped to %s, %s, %s', deprecated_outfile.name,
                ext_ids_outfile.name, urls_outfile.name)


def check_links(entity, catalog):
    catalog_terms = _get_vocabulary(catalog)

    wikidata_links = {}
    to_deprecate = defaultdict(set)
    to_add = defaultdict(set)

    # Target links
    target_links = _gather_target_links(entity, catalog)

    # Wikidata links
    _gather_identifiers(entity, catalog, catalog_terms['pid'], wikidata_links)
    url_pids, ext_id_pids_to_urls = _gather_relevant_pids()
    _gather_wikidata_links(wikidata_links, url_pids, ext_id_pids_to_urls)

    # Check
    _assess(wikidata_links, target_links, to_deprecate, to_add)

    # Separate external IDs from URLs
    ext_ids_to_add, urls_to_add = _extract_ids_from_urls(
        to_add, ext_id_pids_to_urls)

    LOGGER.info('Check completed. %d %s IDs to be deprecated, %d external IDs to be added, %d URL statements to be added', len(
        to_deprecate), catalog, len(ext_ids_to_add), len(urls_to_add))

    return to_deprecate, ext_ids_to_add, urls_to_add, wikidata_links


@click.command()
@click.argument('entity', type=click.Choice(HANDLED_ENTITIES.keys()))
@click.argument('catalog', type=click.Choice(TARGET_CATALOGS.keys()))
@click.option('--wikidata-dump/--no-wikidata-dump', default=False, help='Dump metadata gathered from Wikidata')
@click.option('--upload/--no-upload', default=True, help='Upload check results to Wikidata')
@click.option('--sandbox/--no-sandbox', default=False, help='Upload to the Wikidata sandbox item Q4115189')
@click.option('-d', '--deprecated-outfile', type=click.File('w'), default='output/deprecated_ids.json', help="default: 'output/deprecated_ids.json'")
@click.option('-a', '--added-outfile', type=click.File('w'), default='output/statements_to_be_added.tsv', help="default: 'output/statements_to_be_added.tsv'")
@click.option('-w', '--wikidata-outfile', type=click.File('w'), default='output/wikidata_metadata.json', help="default: 'output/wikidata_metadata.json'")
def check_metadata_cli(entity, catalog, wikidata_dump, upload, sandbox, deprecated_outfile, added_outfile, wikidata_outfile):
    to_deprecate, to_add, wikidata = check_metadata(
        entity, catalog)

    if wikidata_dump and wikidata:
        json.dump({qid: {data_type: list(values) for data_type, values in data.items()}
                   for qid, data in wikidata.items()}, wikidata_outfile, indent=2, ensure_ascii=False)
        LOGGER.info('Wikidata metadata dumped to %s', wikidata_outfile.name)
    if upload:
        # TODO upload_metadata(to_deprecate, to_add, catalog, sandbox)
        pass

    if to_deprecate:
        json.dump({target_id: list(qids) for target_id,
                   qids in to_deprecate.items()}, deprecated_outfile, indent=2)
    if to_add:
        added_outfile.writelines(
            ['\t'.join(triple) + '\n' for triple in to_add])

    LOGGER.info('Result dumped to %s, %s',
                deprecated_outfile.name, added_outfile.name)


def check_metadata(entity, catalog):
    catalog_terms = _get_vocabulary(catalog)

    to_deprecate = defaultdict(set)
    to_add = defaultdict(set)
    wikidata_meta = {}

    # Target metadata
    target_metadata = _gather_target_metadata(entity, catalog)
    for row in target_metadata:
        if row is None:
            return to_deprecate, to_add, wikidata_meta

    # Wikidata metadata
    _gather_identifiers(entity, catalog, catalog_terms['pid'], wikidata_meta)
    # TODO _gather_wikidata_meta(wikidata_meta)

    # Check
    # TODO _assess(wikidata_meta, target_meta, to_deprecate, to_add)

    return to_deprecate, to_add, wikidata_meta


def _gather_target_metadata(entity_type, catalog):
    catalog_constants = _get_catalog_constants(catalog)
    catalog_entity = _get_catalog_entity(entity_type, catalog_constants)

    LOGGER.info('Gathering %s metadata ...', catalog)
    entity = catalog_entity['entity']
    # Base metadata
    query_fields = [entity.catalog_id, entity.born,
                    entity.born_precision, entity.died, entity.died_precision]
    # Check additional metadata ('gender', 'birth_place', 'death_place'):
    if hasattr(entity, 'gender'):
        query_fields.append(entity.gender)
    else:
        LOGGER.info('%s %s has no gender information', catalog, entity_type)
    if hasattr(entity, 'birth_place'):
        query_fields.append(entity.birth_place)
    else:
        LOGGER.info('%s %s has no birth place information',
                    catalog, entity_type)
    if hasattr(entity, 'death_place'):
        query_fields.append(entity.death_place)
    else:
        LOGGER.info('%s %s has no death place information',
                    catalog, entity_type)
    session = _connect_to_db()
    query = session.query(
        *query_fields).filter(or_(entity.born.isnot(None), entity.died.isnot(None)))
    count = query.count()
    if count == 0:
        LOGGER.warning(
            "No validation metadata available for %s. Stopping here", catalog)
        yield None
    LOGGER.info('Got %d metadata rows from %s', count, catalog)
    for row in query.all():
        yield row


def _gather_target_links(entity, catalog):
    catalog_constants = _get_catalog_constants(catalog)
    catalog_entity = _get_catalog_entity(entity, catalog_constants)

    LOGGER.info('Gathering %s links ...', catalog)
    target_links = defaultdict(list)
    count = 0
    link_entity = catalog_entity['link_entity']
    session = _connect_to_db()
    result = session.query(link_entity.catalog_id, link_entity.url).all()
    for row in result:
        target_links[row.catalog_id].append(row.url)
        count += 1
    LOGGER.info('Got %d links from %d %s identifiers',
                count, len(target_links), catalog)
    return target_links


def _get_catalog_entity(entity, catalog_constants):
    catalog_entity = catalog_constants.get(entity)
    if not catalog_entity:
        raise ValueError('Bad entity type: %s. Please use one of %s' %
                         (entity, catalog_constants.keys()))
    return catalog_entity


def _assess(source, target, to_deprecate, to_add):
    LOGGER.info('Starting check against target links ...')
    for qid, data in source.items():
        identifiers = data['identifiers']
        source_links = data.get('links')
        if not source_links:
            LOGGER.warning('Skipping check: no links available in QID %s', qid)
            continue
        for target_id in identifiers:
            if target_id in target.keys():
                target_links = target.get(target_id)
                if not target_links:
                    LOGGER.warning(
                        'Skipping check: no links available in target ID %s', target_id)
                    continue
                target_links = set(target_links)
                shared_links = source_links.intersection(target_links)
                extra_links = target_links.difference(source_links)
                if not shared_links:
                    LOGGER.debug(
                        'No shared links between %s and %s. The identifier statement will be deprecated', qid, target_id)
                    to_deprecate[target_id].add(qid)
                else:
                    LOGGER.debug('%s and %s share these links: %s',
                                 qid, target_id, shared_links)
                if extra_links:
                    LOGGER.debug(
                        '%s has extra links that will be added to %s: %s', target_id, qid, extra_links)
                    to_add[qid].update(extra_links)
                else:
                    LOGGER.debug('%s has no extra links', target_id)


def _extract_ids_from_urls(to_add, ext_id_pids_to_urls):
    LOGGER.info('Starting extraction of IDs from target links to be added ...')
    ext_ids_to_add = []
    urls_to_add = []
    for qid, urls in to_add.items():
        for url in urls:
            ext_id, pid = url_utils.get_external_id_from_url(
                url, ext_id_pids_to_urls)
            if ext_id:
                ext_ids_to_add.append((qid, pid, ext_id))
            else:
                urls_to_add.append(
                    (qid, vocabulary.DESCRIBED_AT_URL, url))
    return ext_ids_to_add, urls_to_add


def _get_vocabulary(catalog):
    catalog_terms = vocabulary.CATALOG_MAPPING.get(catalog)
    if not catalog_terms:
        raise ValueError('Bad catalog: %s. Please use one of %s' %
                         (catalog, vocabulary.CATALOG_MAPPING.keys()))
    return catalog_terms


def _get_catalog_constants(catalog):
    catalog_constants = TARGET_CATALOGS.get(catalog)
    if not catalog_constants:
        raise ValueError('Bad catalog: %s. Please use on of %s' %
                         (catalog, TARGET_CATALOGS.keys()))
    return catalog_constants


def _gather_wikidata_links(wikidata, url_pids, ext_id_pids_to_urls):
    LOGGER.info(
        'Gathering Wikidata sitelinks, third-party links, and external identifier links. This will take a while ...')
    total = 0
    for result in api_requests.get_links(wikidata.keys(), url_pids, ext_id_pids_to_urls):
        for qid, url in result.items():
            if not wikidata[qid].get('links'):
                wikidata[qid]['links'] = set()
            wikidata[qid]['links'].add(url)
            total += 1
    LOGGER.info('Got %d links', total)


def _gather_relevant_pids():
    url_pids = set()
    for result in sparql_queries.url_pids_query():
        url_pids.add(result)
    ext_id_pids_to_urls = defaultdict(dict)
    for result in sparql_queries.external_id_pids_and_urls_query():
        for pid, formatters in result.items():
            for formatter_url, formatter_regex in formatters.items():
                if formatter_regex:
                    try:
                        compiled_regex = re.compile(formatter_regex)
                    except re.error:
                        LOGGER.debug(
                            "Using 'regex' third-party library. Formatter regex not supported by the 're' standard library: %s", formatter_regex)
                        compiled_regex = regex.compile(formatter_regex)
                else:
                    compiled_regex = None
                ext_id_pids_to_urls[pid][formatter_url] = compiled_regex
    return url_pids, ext_id_pids_to_urls


def _gather_identifiers(entity, catalog, catalog_pid, aggregated):
    catalog_constants = _get_catalog_constants(catalog)
    LOGGER.info('Gathering %s identifiers ...', catalog)
    query_type = 'identifier', HANDLED_ENTITIES.get(entity)
    for result in sparql_queries.run_identifier_or_links_query(query_type, catalog_constants[entity]['qid'], catalog_pid, 0):
        for qid, target_id in result.items():
            if not aggregated.get(qid):
                aggregated[qid] = {'identifiers': set()}
            aggregated[qid]['identifiers'].add(target_id)
    LOGGER.info('Got %d %s identifiers', len(aggregated), catalog)


def upload_links(to_deprecate, ext_ids_to_add, urls_to_add, catalog, sandbox):
    catalog_terms = _get_vocabulary(catalog)
    catalog_qid = catalog_terms['qid']
    LOGGER.info('Starting deprecation of %s IDs ...', catalog)
    wikidata_bot.delete_or_deprecate_identifiers(
        'deprecate', to_deprecate, catalog, sandbox)
    LOGGER.info('Starting addition of external IDs to Wikidata ...')
    wikidata_bot.add_statements(ext_ids_to_add, catalog_qid, sandbox)
    LOGGER.info('Starting addition of URL statements to Wikidata ...')
    wikidata_bot.add_statements(urls_to_add, catalog_qid, sandbox)
