import astropy.units as u
import numpy as np
import pyvo
import requests

__all__ = ['search_code_mpc']


def search_code_mpc(code):
    """Reads the Minor Planet Center (MPC) Observer codes SBN mirror (mpc_sbn).

    Returns
    -------
    name : `str`
        Observatory name from the MPC database.

    site : `astropy.coordinates.EarthLocation`
        Observatory site as an Astropy EarthLocation object.
    """
    from astropy.coordinates import EarthLocation
    import warnings
    
    url = "https://userquery.linea.org.br/tap"
    session = requests.Session()
    tap = pyvo.dal.TAPService(url, session=session)
    
    query = f"SELECT * FROM mpc_sbn.obscodes WHERE obscode = '{code}'"
    warnings.warn(f'Querying code {code} in the Linea MPC Observer Database...')
    result = tap.run_sync(query)
    table = result.to_table()

    if len(table) == 0:
        raise ValueError(f'code {code} could not be located in MPC database')

    line = table[0]
    lon = line['longitude'] * u.deg
    rcphi = line['rhocosphi'] * 6378.137 * u.km
    rsphi = line['rhosinphi'] * 6378.137 * u.km
    name = line['name']
    site = EarthLocation.from_geocentric(rcphi * np.cos(lon),
                                         rcphi * np.sin(lon),
                                         rsphi)
    return name, site
