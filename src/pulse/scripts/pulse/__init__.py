
import os
import logging

from .version import __version__
from .core import *
from .loader import *


LOG = logging.getLogger("pulse")
LOG.level = logging.DEBUG

BUILTIN_ACTIONS_LOADED = False

def loadActionsFromDirectory(startDir):
    """
    Search for and load BuildActions from the given directory,
    then register them for use.

    Args:
        startDir: A str path of the directory to search
    """
    loader = BuildActionLoader()
    for config, action in loader.loadActionsFromDirectory(startDir):
        registerAction(config, action)


def loadBuiltinActions():
    """
    Load all built-in pulse actions.
    """
    global BUILTIN_ACTIONS_LOADED
    if not BUILTIN_ACTIONS_LOADED:
        actionsDir = os.path.join(os.path.dirname(__file__), 'actions')
        loadActionsFromDirectory(actionsDir)
        BUILTIN_ACTIONS_LOADED = True
