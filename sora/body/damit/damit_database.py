import pandas as pd
import sqlite3
import requests
import hashlib
import os
import json
from io import StringIO
from datetime import datetime, timedelta
import logging

from astropy.coordinates import SkyCoord
from astropy.time import Time
from tqdm import tqdm
import astropy.units as u

__all__ = ['DamitDB']

damit_urls = {
    "asteroids": "https://astro.troja.mff.cuni.cz/projects/damit/exports/table/asteroids",
    "models": "https://astro.troja.mff.cuni.cz/projects/damit/exports/table/asteroid_models",
    "references": "https://astro.troja.mff.cuni.cz/projects/damit/exports/table/references",
    "model_references": "https://astro.troja.mff.cuni.cz/projects/damit/exports/table/asteroid_models_references",
    "tumblers": "https://astro.troja.mff.cuni.cz/projects/damit/exports/table/tumblers",
    "references_tumblers": "https://astro.troja.mff.cuni.cz/projects/damit/exports/table/references_tumblers"
}


class DamitDB:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DamitDB, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path="asteroids.db", update_age_days=30, verbose=False):
        if hasattr(self, '_initialized') and self._initialized:
            return  # Avoid reinitialization
        self.db_path = db_path
        self.hash_file = "hashes.json"
        self.schema_file = "schema_cache.json"
        self.last_update_file = "last_update.txt"
        self.update_age_days = update_age_days
        self.verbose = verbose
        self.dataframes = {}
        self.conn = None
        self._initialized = True

    def get_data(self, url):
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.text.strip()

    def load_hashes(self):
        if os.path.exists(self.hash_file):
            with open(self.hash_file, "r") as f:
                return json.load(f)
        return {}

    def save_hashes(self, hash_dict):
        with open(self.hash_file, "w") as f:
            json.dump(hash_dict, f, indent=2)

    def load_schema_cache(self):
        if os.path.exists(self.schema_file):
            with open(self.schema_file, "r") as f:
                return json.load(f)
        return {}

    def save_schema_cache(self, schema):
        with open(self.schema_file, "w") as f:
            json.dump(schema, f, indent=2)

    def should_update(self):
        if not os.path.exists(self.last_update_file):
            return True
        with open(self.last_update_file, "r") as f:
            try:
                last = datetime.fromisoformat(f.read().strip())
            except ValueError:
                return True
        return datetime.now() - last > timedelta(days=self.update_age_days)

    def mark_updated(self):
        with open(self.last_update_file, "w") as f:
            f.write(datetime.now().isoformat())

    def open_connection(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON")

    def close_connection(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    def create_table(self, name, df, foreign_keys=None):
        schema = {}
        cols = []
        for col in df.columns:
            col_type = "TEXT"
            if pd.api.types.is_numeric_dtype(df[col]):
                col_type = "REAL" if df[col].dtype.kind == "f" else "INTEGER"
            if col.lower() == "id":
                cols.append(f"{col} TEXT PRIMARY KEY")
            else:
                cols.append(f"{col} {col_type}")
            schema[col] = col_type
        if foreign_keys:
            for fk in foreign_keys:
                cols.append(f"FOREIGN KEY ({fk['from']}) REFERENCES {fk['table']}({fk['to']}) ON DELETE CASCADE")
        col_sql = ",\n".join(cols)
        self.conn.execute(f"DROP TABLE IF EXISTS {name}")
        self.conn.execute(f"CREATE TABLE {name} (\n{col_sql}\n)")
        return schema

    def validate_foreign_keys(self):
        dfs = self.dataframes

        def filter_df(df_name, ref_col, ref_df, ref_id):
            if ref_col in dfs[df_name].columns:
                dfs[df_name] = dfs[df_name][dfs[df_name][ref_col].isin(dfs[ref_df][ref_id])]

        filter_df("models", "asteroid_id", "asteroids", "id")
        filter_df("model_references", "asteroid_model_id", "models", "id")
        filter_df("model_references", "reference_id", "references", "id")
        filter_df("tumblers", "asteroid_id", "asteroids", "id")
        filter_df("references_tumblers", "tumbler_id", "tumblers", "id")
        filter_df("references_tumblers", "reference_id", "references", "id")

    def update_database(self, force=False):
        if not force and not self.should_update():
            logging.info("Damit database is up to date.")
            return

        self.open_connection()
        current_hashes = self.load_hashes()
        schema_cache = self.load_schema_cache()
        new_hashes = {}

        fk_map = {
            "models": [{"from": "asteroid_id", "table": "asteroids", "to": "id"}],
            "model_references": [
                {"from": "asteroid_model_id", "table": "asteroid_models", "to": "id"},
                {"from": "reference_id", "table": "damit_references", "to": "id"}
            ],
            "tumblers": [{"from": "asteroid_id", "table": "asteroids", "to": "id"}],
            "references_tumblers": [
                {"from": "tumbler_id", "table": "tumblers", "to": "id"},
                {"from": "reference_id", "table": "damit_references", "to": "id"}
            ]
        }

        for key, url in tqdm(damit_urls.items(), desc="Updating DAMIT Database"):
            try:
                text = self.get_data(url)
                hash_val = hashlib.sha256(text.encode()).hexdigest()
                new_hashes[key] = hash_val

                if current_hashes.get(key) == hash_val:
                    continue

                df = pd.read_csv(StringIO(text), sep=",", quotechar='"')
                self.dataframes[key] = df

                table_name = "damit_references" if key == "references" else key if key != "models" else "asteroid_models"
                schema = self.create_table(table_name, df, fk_map.get(key))
                schema_cache[table_name] = schema
                df.to_sql(table_name, self.conn, if_exists="append", index=False)

            except Exception as e:
                logging.error(f"Error processing table {key}: {e}")

        self.save_hashes(new_hashes)
        self.save_schema_cache(schema_cache)
        self.mark_updated()
        self.close_connection()
        logging.info("Damit database update completed.")

    def get_model_by_name(self, name):
        self.open_connection()
        query = """
                SELECT m.*
                FROM asteroid_models m
                         JOIN asteroids a ON m.asteroid_id = a.id
                WHERE a.name = ? \
                """
        df = pd.read_sql_query(query, self.conn, params=(name,))
        self.close_connection()
        return df

    def get_references_by_model(self, model_id):
        self.open_connection()
        query = """
                SELECT r.*
                FROM damit_references r
                         JOIN asteroid_models_references amr ON amr.reference_id = r.id
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
                FROM asteroid_models
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
    def asteroid_models(self):
        """Return the 'asteroid_models' table as a DataFrame."""
        self.open_connection()
        try:
            return pd.read_sql_query("SELECT * FROM asteroid_models", self.conn)
        except Exception as e:
            logging.error(f"Error fetching asteroid_models table: {e}")
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
    def asteroid_models_references(self):
        """Return the 'asteroid_models_references' table as a DataFrame."""
        self.open_connection()
        try:
            return pd.read_sql_query("SELECT * FROM asteroid_models_references", self.conn)
        except Exception as e:
            logging.error(f"Error fetching asteroid_models_references table: {e}")
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
