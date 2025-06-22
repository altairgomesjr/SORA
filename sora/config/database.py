import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, Any

import pandas as pd
import requests
from tqdm import tqdm

from sora.config.core import Config

config = Config()


def load_json(json_file) -> Dict[str, Any]:
    if os.path.exists(json_file):
        with open(json_file, "r") as f:
            return json.load(f)
    return {}


def save_json(file_path: str, data: Dict[str, Any]):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


class BaseDatabase:
    _log_messages = {
        "updated": "Database is up to date.",
        "updating": "Updating database.",
    }
    _fk_map = {}
    _urls = {}

    def __init__(self, config_section_data):
        if hasattr(self, '_initialized') and self._initialized:
            return  # Avoid reinitialization
        self._section_data = config_section_data
        self.db_path = config.data_path / config_section_data.database
        self._json_file = config.data_path / config_section_data.json_data
        self._json_data = load_json(self._json_file)
        self.data_dir = config.data_path / config_section_data.data_dir
        self.update_age_days = config_section_data.update_age_days
        self.dataframes = {}
        self.conn = None
        self._initialized = True

    def _load_config(self):
        self._section_data = self._section_data
        self.db_path = config.data_path / self._section_data.database
        self._json_file = config.data_path / self._section_data.json_data
        self._json_data = load_json(self._json_file)
        self.data_dir = config.data_path / self._section_data.data_dir
        self.update_age_days = self._section_data.update_age_days

    def open_connection(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA foreign_keys = ON")
            logging.debug("Opened database connection to '%s'" % self.db_path)

    def close_connection(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None
            logging.debug("Closed database connection to '%s'" % self.db_path)

    def should_update(self) -> bool:
        last_update = self._json_data.get('last_update', '')
        if not last_update:
            return True
        last = datetime.fromisoformat(last_update)
        return datetime.now() - last > timedelta(days=self.update_age_days)

    def _create_table(self, name, df, foreign_keys=None):
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

    def _get_data(self, url):
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.text.strip()

    def update_database(self, force=False):
        if not force and not self.should_update():
            logging.info(self._log_messages["updated"])
            return

        current_hashes = self._json_data.get('hash', {})
        schema_cache = self._json_data.get('schema_cache', {})
        new_hashes = {}

        self.open_connection()
        for key, url in tqdm(self._urls.items(), desc=self._log_messages["updating"]):
            try:
                text = self._get_data(url)
                hash_val = hashlib.sha256(text.encode()).hexdigest()
                if current_hashes.get(key) == hash_val:
                    continue

                df = pd.read_csv(StringIO(text), sep=",", quotechar='"')
                schema = self._create_table(key, df, self._fk_map.get(key))
                schema_cache[key] = schema
                df.to_sql(key, self.conn, if_exists='replace', index=False)
                new_hashes[key] = hash_val

            except Exception as e:
                logging.error(f"Error processing table {key}: {e}")
                raise

        new_data = {"hash": new_hashes, "schema_cache": schema_cache, "last_update": datetime.now().isoformat()}
        save_json(self._json_file, new_data)
        self.close_connection()
        self._load_config()
        logging.info(self._log_messages["updated"])

    def _ensure_column(self, table, colname, coltype='TEXT'):
        """Add column to table if it does not exist."""
        self.open_connection()
        try:
            with self.conn:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {colname} {coltype}")
                logging.debug(f"Column '{colname}' added to table '{table}'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                logging.debug(f"Column '{colname}' exists.")
            else:
                logging.error(f"Error adding columns {colname}: {e}")
                raise
        self.close_connection()
