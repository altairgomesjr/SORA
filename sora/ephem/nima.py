import os
import time
import logging
import requests
import pandas as pd
from tqdm import tqdm
from urllib.parse import urlparse
from sora.config.core import Config
from sora.config.database import BaseDatabase

config = Config()

class NimaDB(BaseDatabase):
    _instance = None  # Singleton reference
    _urls = {
        "nima_table": 'https://lesia.obspm.fr/lucky-star/nimacsv.php'
    }
    _log_messages = {
        'updated': "NIMA database is up to date.",
        "updating": "Updating NIMA database.",
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NimaDB, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        super(NimaDB, self).__init__(config.nima)

    def show_table(self, limit=None, filter_condition=None):
        """Display rows from the nima_table table using pandas."""
        # Ensure table exists
        # self.update_database()

        query = "SELECT * FROM nima_table"
        if filter_condition:
            query += f" WHERE {filter_condition}"
        if limit:
            query += f" LIMIT {limit}"

        self.open_connection()
        try:
            df = pd.read_sql_query(query, self.conn)
            print(df)
        except Exception as e:
            logging.error(f"NIMA: Failed to show table: {e}")
            print(f"Error: {e}")
        self.close_connection()

    def download_all_bspfiles(self, retries=3):
        os.makedirs(self.data_dir, exist_ok=True)
        base_query = "SELECT name, bspfile FROM nima_table WHERE bspfile IS NOT NULL"

        self.open_connection()
        cursor = self.conn.cursor()
        cursor.execute(base_query)
        rows = cursor.fetchall()

        for name, bsp_url in tqdm(rows, desc="NIMA: Downloading BSP files"):
            if not bsp_url:
                continue

            filename = os.path.basename(urlparse(bsp_url).path)
            filepath = os.path.join(self.data_dir, filename)

            if os.path.exists(filepath):
                continue

            for attempt in range(retries):
                try:
                    response = requests.get(bsp_url, timeout=15)
                    response.raise_for_status()
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    with self.conn:
                        self.conn.execute("""
                                          UPDATE nima_table
                                          SET bspfilepath = ?
                                          WHERE name = ?
                                          """, (os.path.abspath(filepath), name))
                    break
                except Exception as e:
                    if attempt == retries - 1:
                        logging.error(f"NIMA: Failed to download {bsp_url} for {name}: {e}")
                    else:
                        time.sleep(2 ** attempt)
        self.close_connection()

    def get_bspfile(self, name):
        """
        Return the local path to the BSP file and idSPK for a given name or designation.

        Returns:
            tuple (path: str or None, idSPK: int or None)
        """
        if self.should_update():
            self.update_database()

        self._ensure_column(table="nima_table", colname="bspfilepath")
        query = """
                SELECT bspfile, idSPK, bspfilepath \
                FROM nima_table
                WHERE (LOWER(name) = ? OR LOWER(designation) = ? or LOWER(number) = ?) \
                  AND bspfile IS NOT NULL \
                """
        self.open_connection()
        cursor = self.conn.cursor()
        name = str(name).replace(" ", "").lower()
        cursor.execute(query, (name, name, name))
        row = cursor.fetchone()

        if row is None:
            logging.error(f"NIMA: Object {name} not found on database")
            raise ValueError(f"NIMA: Object {name} not found on database")

        bsp_url, idspk, bsp_path = row
        os.makedirs(self.data_dir, exist_ok=True)
        filename = os.path.basename(urlparse(bsp_url).path)
        filepath = os.path.join(self.data_dir, filename)

        if os.path.exists(filepath):
            return filepath, idspk
        elif bsp_path is not None:
            logging.warning(f"NIMA: BSP file listed in DB but not found on disk: {filepath}")

        try:
            logging.info(f"Downloading BSP file {filename} from {bsp_url}")
            response = requests.get(bsp_url, timeout=15)
            response.raise_for_status()
            with open(filepath, 'wb') as f, tqdm(
                desc = filename,
                total = int(response.headers.get('content-length', 0)),
                unit='B',
                unit_scale = True,
                unit_divisor = 1024,
            ) as bar:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bar.update(len(chunk))
            logging.info(f"NIMA: Downloaded {filename} for {name}")
        except Exception as e:
            logging.error(f"NIMA: Failed to download {bsp_url} for {name}: {e}")
            raise

        # Update data to database
        with self.conn:
            self.conn.execute("""
                              UPDATE nima_table
                              SET bspfilepath = ?
                              WHERE idSPK = ?
                              """, (os.path.abspath(filepath), idspk))
        self.close_connection()

        return os.path.abspath(filepath), idspk