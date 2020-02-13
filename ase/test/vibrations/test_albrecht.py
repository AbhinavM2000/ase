import pytest

from ase.calculators.h2morse import H2Morse, H2MorseExcitedStates
from ase.vibrations.albrecht import Albrecht


def test_overlap():
    name = 'rrmorse'
    atoms = H2Morse()
    om = 1
    gam = 0.1

    ao = Albrecht(atoms, H2MorseExcitedStates,
                  gsname=name, exname=name,
                  overlap=lambda x, y: x.overlap(y),
                  approximation='Albrecht A', txt=None)
    ao.run()

    """One state only"""
    
    ao = Albrecht(atoms, H2MorseExcitedStates, exkwargs={'nstates': 1},
                  gsname=name, exname=name, overlap=True,
                  approximation='Albrecht A', txt=None)
    aoi = ao.absolute_intensity(omega=om, gamma=gam)[-1]
    
    al = Albrecht(atoms, H2MorseExcitedStates, exkwargs={'nstates': 1},
                  gsname=name, exname=name,
                  approximation='Albrecht A', txt=None)
    ali = al.absolute_intensity(omega=om, gamma=gam)[-1]
    assert ali == pytest.approx(aoi, 1e-9)

    """Include degenerate states"""
    
    ao = Albrecht(atoms, H2MorseExcitedStates,
                  gsname=name, exname=name, overlap=True,
                  approximation='Albrecht A', txt=None)
    aoi = ao.absolute_intensity(omega=om, gamma=gam)[-1]

    al = Albrecht(atoms, H2MorseExcitedStates,
                  gsname=name, exname=name,
                  approximation='Albrecht A', txt=None)
    ali = al.absolute_intensity(omega=om, gamma=gam)[-1]
    assert ali == pytest.approx(aoi, 1e-5)


def main():
    test_overlap()

if __name__ == '__main__':
    main()
