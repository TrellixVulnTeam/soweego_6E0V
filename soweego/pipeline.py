"""Module to run full soweego pipeline"""

import gc
import logging
from typing import Callable

import click
import objgraph
from mem_top import mem_top

from soweego.commons import target_database
from soweego.commons.db_manager import DBManager
from soweego.importer.importer import check_links_cli as validate_links
from soweego.importer.importer import import_cli
from soweego.linker import classify, evaluate, train
from soweego.validator.checks import bio_cli, dead_ids_cli, links_cli

LOGGER = logging.getLogger(__name__)


@click.command()
@click.argument(
    'target', type=click.Choice(target_database.supported_targets())
)
@click.option(
    '--validator/--no-validator',
    default=False,
    help='Executes the validation steps for the target. Default: no.',
)
@click.option(
    '--importer/--no-importer',
    default=True,
    help='Executes the importer steps for the target. Default: yes.',
)
@click.option(
    '--linker/--no-linker',
    default=True,
    help='Executes the linker steps for the target. Default: yes.',
)
@click.option(
    '--upload/--no-upload',
    default=True,
    help='Upload the results on wikidata. Default: yes.',
)
@click.option(
    '-c',
    '--credentials-path',
    type=click.Path(file_okay=True),
    default=None,
    help="default: None",
)
def cli(
    target: str,
    validator: bool,
    importer: bool,
    linker: bool,
    upload: bool,
    credentials_path: str,
):
    """Executes importer/linker and optionally validator for a target"""

    if credentials_path:
        LOGGER.info("Using database credentials from file %s", credentials_path)
        DBManager.set_credentials_from_path(credentials_path)

    if importer:
        _importer(target)
    else:
        LOGGER.info("Skipping importer")

    if linker:
        _linker(target, upload)
    else:
        LOGGER.info("Skipping linker")

    if validator:
        _validator(target, upload)
    else:
        LOGGER.info("Skipping validator")


def _importer(target: str):
    """Contains all the command the importer has to do"""
    LOGGER.info(
        "Running importer for target: %s without resolving the URLs", target
    )
    _invoke_no_exit(import_cli, [target])
    LOGGER.info("Validating URL resolving them for target %s", target)
    _invoke_no_exit(validate_links, [target])


def _linker(target: str, upload: bool):
    """Contains all the command the linker has to do"""
    LOGGER.info("Running linker for target: %s", target)
    upload_option = "--upload" if upload else "--no-upload"
    for target_type in target_database.supported_entities_for_target(target):
        if not target_type:
            continue
        _invoke_no_exit(evaluate.cli, ['slp', target, target_type])
        _invoke_no_exit(train.cli, ['slp', target, target_type])
        _invoke_no_exit(
            classify.cli, ['slp', target, target_type, upload_option]
        )


def _validator(target: str, upload: bool):
    """Contains all the command the validator has to do"""
    args = [target, '--upload'] if upload else [target]
    # Runs the validator for each kind of entity of the given target database
    for entity_type in target_database.supported_entities_for_target(target):
        args.insert(1, entity_type)
        LOGGER.info("Running validator for target %s %s", target, entity_type)
        _invoke_no_exit(dead_ids_cli, args)
        _invoke_no_exit(links_cli, args)
        _invoke_no_exit(bio_cli, args)


def _invoke_no_exit(function: Callable, args: list):
    """Given a function avoids that it exits the program"""
    try:
        function(args)
    except SystemExit:
        pass
    LOGGER.debug("GC collect %s\n" % gc.collect())
    LOGGER.debug("memtop: %s\n" % mem_top())
    LOGGER.debug("objgraph: %s\n" % objgraph.show_growth())
