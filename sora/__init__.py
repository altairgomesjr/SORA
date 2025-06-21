from .body import Body
from .config.core import Config
from .config.logging import configure_logger
from .ephem import EphemKernel, EphemPlanete, EphemJPL, EphemHorizons
from .lightcurve import LightCurve
from .observer import Observer, Spacecraft
from .star import Star
from .occultation import Occultation
import logging


__all__ = ['Body', 'Config', 'EphemKernel', 'EphemPlanete', 'EphemJPL', 'EphemHorizons',
           'LightCurve', 'Observer', 'Spacecraft', 'Star', 'Occultation']

__version__ = '0.3.2'

config = Config()
configure_logger()

logging.info(f'SORA started, version: {__version__}')
