import astropy.units as u
from astropy.coordinates import SkyCoord
from sora.body.frame import PlanetocentricFrame, Kaasalainen

__all__ = ['archinal_to_kaasalainen', 'kaasalainen_to_archinal']


def archinal_to_kaasalainen(pole, w):
    """ Convert Pole coordinates and Prime Angle from IAU transformation to Kaasalainen transformation.

    Parameters
    ----------
    pole : `astropy.coordinates.SkyCoord`, `str`
        The pole coordinates in the ICRS
    w : `float`
        The Prime Angle in the IAU transformation

    Returns
    -------
    pole : `astropy.coordinates.SkyCoord`
        The pole in the Barycentrin Mean Ecliptic coordinates
    phi : `float`
        The Prime Angle in the Kaasalainen transformation

    """
    archinal = PlanetocentricFrame(pole=pole, prime_angle=w)
    origin = SkyCoord(*[1, 0, 0] * u.km, frame=archinal, representation_type='cartesian')
    k_pole = SkyCoord(archinal.pole).barycentricmeanecliptic
    kaasa = Kaasalainen(pole=k_pole, right_hand=True)
    phi = origin.transform_to(kaasa).lon.deg
    return k_pole.to_string('decimal'), phi


def kaasalainen_to_archinal(pole, phi):
    """ Convert Pole coordinates and Phi Angle from Kaasalainen transformation to IAU transformation.

    Parameters
    ----------
    pole : `astropy.coordinates.SkyCoord`, `str`
        The pole in the Barycentric Mean Ecliptic coordinates
    phi : `float`
        The Prime Angle in the Kaasalainen transformation

    Returns
    -------
    pole : `astropy.coordinates.SkyCoord`, `str`
        The pole coordinates in the ICRS
    w : `float`
        The Prime Angle in the IAU transformation

    """
    kaasa = Kaasalainen(pole=pole, phi=phi)
    origin = SkyCoord(*[1, 0, 0] * u.km, frame=kaasa, representation_type='cartesian')
    a_pole = SkyCoord(kaasa.pole).icrs
    archinal = PlanetocentricFrame(pole=a_pole, right_hand=True)
    w = origin.transform_to(archinal).lon.deg
    return a_pole.to_string('decimal'), w
