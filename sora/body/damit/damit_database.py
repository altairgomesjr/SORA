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

    def get_model_by_name(self, name, latest_only: bool = False):
        """
        Retrieves asteroid models associated with a given asteroid name.

        Parameters
        ----------
        name : str
            The name of the asteroid.
        latest_only : bool, default False
            If True, return only the most recently modified model.

        Returns
        -------
        pd.DataFrame
            Model data.
        """
        self.open_connection()
        query = """
                SELECT m.*
                FROM models m
                JOIN asteroids a ON m.asteroid_id = a.id
                WHERE LOWER(a.name) = LOWER(?) \
                """
        if latest_only:
            query += " ORDER BY m.version DESC LIMIT 1"
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
        self._ensure_column(table='models', colname='shape_path')

        # Check if it already exists on the database
        self.open_connection()
        query = "SELECT shape_path FROM models WHERE id = ?"
        row = self.conn.execute(query, (model_id,)).fetchone()

        if row and row[0]:
            shape_path = row[0]
            if os.path.exists(shape_path):
                return os.path.abspath(shape_path)
            else:
                logging.warning(f"DAMIT: Model {model_id} path in DB is missing on disk. Re-downloading.")
        if row is None:
            logging.error(f"DAMIT: Model {model_id} does not exist on Damit database.")
            raise ValueError(f"Model {model_id} does not exist on Damit database.")

        base_url = "https://damit.cuni.cz/projects/damit/generated_files/open/AsteroidModel"
        model_filename = f"shape_{model_id}.obj"
        os.makedirs(self.data_dir, exist_ok=True)
        model_path = os.path.join(self.data_dir, model_filename)

        if not os.path.exists(model_path):
            url = f"{base_url}/{model_id}/shape.obj"
            try:
                logging.info(f"DAMIT: Downloading model {model_id} from {url}")
                mystr = self._get_data(url)
                with open(model_path, "w") as f:
                    f.write(mystr)
                logging.info(f"DAMIT: Model {model_id} saved to {model_path}")
            except requests.RequestException as e:
                logging.error(f"DAMIT: Failed to download model {model_id}: {e}")
                raise RuntimeError(f"Download failed for model {model_id}") from e

        # Update data to database
        with self.conn:
            self.conn.execute("""
                              UPDATE models
                              SET shape_path = ?
                              WHERE id = ?
                              """, (os.path.abspath(model_path), model_id))

        return os.path.abspath(model_path)

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
