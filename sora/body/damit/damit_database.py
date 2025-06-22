import pandas as pd
import requests
import os
import logging

from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
from sora.config.core import Config
from sora.config.database import BaseDatabase

__all__ = ['DamitDB']

config = Config()


class DamitDB(BaseDatabase):
    _instance = None
    _fk_map = {
        "models": [{"from": "asteroid_id", "table": "asteroids", "to": "id"}],
        "models_references": [
            {"from": "asteroid_model_id", "table": "models", "to": "id"},
            {"from": "reference_id", "table": "damit_references", "to": "id"}
        ],
        "tumblers": [{"from": "asteroid_id", "table": "asteroids", "to": "id"}],
        "references_tumblers": [
            {"from": "tumbler_id", "table": "tumblers", "to": "id"},
            {"from": "reference_id", "table": "damit_references", "to": "id"}
        ]
    }
    _urls = {
        "asteroids": "https://damit.cuni.cz/exports/table/asteroids",
        "models": "https://damit.cuni.cz/exports/table/asteroid_models",
        "damit_references": "https://damit.cuni.cz/exports/table/references",
        "models_references": "https://damit.cuni.cz/exports/table/asteroid_models_references",
        "tumblers": "https://damit.cuni.cz/exports/table/tumblers",
        "references_tumblers": "https://damit.cuni.cz/exports/table/references_tumblers"
    }
    _log_messages = {
        "updated": "DAMIT database is up to date.",
        "updating": "Updating DAMIT database.",
    }

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DamitDB, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__(config.damit)

    def get_model_by_name(self, name):
        self.open_connection()
        query = """
                SELECT m.*
                FROM models m
                JOIN asteroids a ON m.asteroid_id = a.id
                WHERE LOWER(a.name) = LOWER(?) \
                """
        df = pd.read_sql_query(query, self.conn, params=(name,))
        self.close_connection()
        return df

    def get_references_by_model(self, model_id):
        self.open_connection()
        query = """
                SELECT r.*
                FROM damit_references r
                         JOIN models_references amr ON amr.reference_id = r.id
                WHERE amr.asteroid_model_id = ? \
                """
        df = pd.read_sql_query(query, self.conn, params=(model_id,))
        self.close_connection()
        return df

    def get_spin(self, model_id):
        """Retrieve spin parameters for a given model ID.

        Parameters
        ----------
        model_id : `int`, `str`
            The number containing the ID of the model

        Returns
        -------
        pole : `astropy.coordinates.SkyCoord`
            The Coordinates of the pole in Ecliptic Coordinates

        period : `astropy.units.Quantity`
            The rotational period, in hours

        epoch : `astropy.time.Time`
            The epoch of reference for phi0

        phi0 : `astropy.units.Quantity`
            The prime meridian angle in Kaasalainen transformation, in deg
        """
        self.open_connection()

        query = """
                SELECT "lambda", "beta", "period", "yorp", "jd0", "phi0"
                FROM models
                WHERE id = ? LIMIT 1
                """
        try:
            cursor = self.conn.execute(query, (model_id,))
            row = cursor.fetchone()
            if row:
                keys = ["lambda", "beta", "period", "yorp", "jd0", "phi0"]
                spin_data = dict(zip(keys, row))
                pole = SkyCoord(spin_data['lambda'], spin_data['beta'], unit=(u.deg, u.deg), frame='barycentricmeanecliptic')
                ref_date = Time(spin_data['jd0'], format='jd', scale='tdb')
                period = u.Quantity(spin_data['period'], unit=u.h)
                phi0 = u.Quantity(spin_data['phi0'], unit=u.deg)
                yorp = spin_data['yorp'] if spin_data['yorp'] else 0
                yorp = u.Quantity(yorp, unit=u.rad / u.day ** 2)
                return pole, period, ref_date, phi0, yorp
            else:
                logging.warning(f"No spin data found for model ID: {model_id}")
                return None
        except Exception as e:
            logging.error(f"Error fetching spin data for model ID {model_id}: {e}")
            return pd.DataFrame()

    def get_model(self, model_id):
        """ Downloads the model from DAMIT.
        The model is saved as "shape_xxxx.obj" where xxxx is id of the model

        Parameters
        ----------
        model_id : `int`, `str`
            The number containing the ID of the model to download

        Returns
        -------
        None
        """
        mystr = self.get_data(
            f'https://astro.troja.mff.cuni.cz/projects/damit/generated_files/open/AsteroidModel/{model_id}/shape.obj')
        with open(f'shape_{model_id}.obj', 'w') as f:
            f.write(mystr)

    @property
    def asteroids(self):
        """Return the 'asteroids' table as a DataFrame."""
        self.open_connection()
        try:
            return pd.read_sql_query("SELECT * FROM asteroids", self.conn)
        except Exception as e:
            logging.error(f"Error fetching asteroids table: {e}")
            return pd.DataFrame()

    @property
    def models(self):
        """Return the 'models' table as a DataFrame."""
        self.open_connection()
        try:
            return pd.read_sql_query("SELECT * FROM models", self.conn)
        except Exception as e:
            logging.error(f"Error fetching models table: {e}")
            return pd.DataFrame()

    @property
    def damit_references(self):
        """Return the 'damit_references' table as a DataFrame."""
        self.open_connection()
        try:
            return pd.read_sql_query("SELECT * FROM damit_references", self.conn)
        except Exception as e:
            logging.error(f"Error fetching damit_references table: {e}")
            return pd.DataFrame()

    @property
    def models_references(self):
        """Return the 'models_references' table as a DataFrame."""
        self.open_connection()
        try:
            return pd.read_sql_query("SELECT * FROM models_references", self.conn)
        except Exception as e:
            logging.error(f"Error fetching models_references table: {e}")
            return pd.DataFrame()

    @property
    def tumblers(self):
        """Return the 'tumblers' table as a DataFrame."""
        self.open_connection()
        try:
            return pd.read_sql_query("SELECT * FROM tumblers", self.conn)
        except Exception as e:
            logging.error(f"Error fetching tumblers table: {e}")
            return pd.DataFrame()

    @property
    def references_tumblers(self):
        """Return the 'references_tumblers' table as a DataFrame."""
        self.open_connection()
        try:
            return pd.read_sql_query("SELECT * FROM references_tumblers", self.conn)
        except Exception as e:
            logging.error(f"Error fetching references_tumblers table: {e}")
            return pd.DataFrame()
