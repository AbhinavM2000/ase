from __future__ import print_function, division
# Copyright (C) 2010, Jesper Friis
# (see accompanying license files for details).

import os
import numpy as np
from numpy import pi, sin, cos, arccos, sqrt, dot
from numpy.linalg import norm

from ase.utils.arraywrapper import arraylike

@arraylike
class Cell:
    """Parallel epipedal unit cell of up to three dimensions.

    This wraps a 3x3 array whose [i, j]-th element is the jth
    Cartesian coordinate of the ith unit vector.

    Cells of less than three dimensions are represented by placeholder
    unit vectors that are zero."""

    # This overridable variable tells an Atoms object whether atoms.cell
    # and atoms.get_cell() should be a Cell object or an array.
    _atoms_use_cellobj = 1#bool(os.environ.get('ASE_DEBUG_CELLOBJ'))

    def __init__(self, array=None, pbc=None):
        if array is None:
            array = np.zeros((3, 3))

        if pbc is None:
            pbc = np.ones(3, bool)

        # We could have lazy attributes for structure (bcc, fcc, ...)
        # and other things.  However this requires making the cell
        # array readonly, else people will modify it and things will
        # be out of synch.
        assert array.shape == (3, 3)
        assert array.dtype == float
        assert pbc.shape == (3,)
        assert pbc.dtype == bool
        self.array = array
        self.pbc = pbc

    def cellpar(self, radians=False):
        return cell_to_cellpar(self.array, radians)

    @property
    def shape(self):
        return self.array.shape

    @classmethod
    def new(cls, cell):
        cell = np.array(cell, float)

        if cell.shape == (3,):
            cell = np.diag(cell)
        elif cell.shape == (6,):
            cell = cellpar_to_cell(cell)
        elif cell.shape != (3, 3):
            raise ValueError('Cell must be length 3 sequence, length 6 '
                             'sequence or 3x3 matrix!')

        return cls(cell)

    @classmethod
    def fromcellpar(cls, cellpar, ab_normal=(0, 0, 1), a_direction=None):
        cell = cellpar_to_cell(cellpar, ab_normal, a_direction)
        return Cell(cell)

    #def crystal_structure(self, eps=2e-4, niggli_reduce=True):
    #    return crystal_structure_from_cell(self.array, eps, niggli_reduce)

    def complete(self):
        """Convert missing cell vectors into orthogonal unit vectors."""
        return Cell(complete_cell(self.array))

    def copy(self):
        return Cell(self.array.copy())

    @property
    def dtype(self):
        return self.array.dtype

    @property
    def size(self):
        return self.array.size

    @property
    def T(self):
        return self.array.T

    @property
    def flat(self):
        return self.array.flat

    @property
    def celldim(self):
        # XXX Would name it ndim, but this clashes with ndarray.ndim
        return self.array.any(1).sum()

    @property
    def orthorhombic(self):
        return orthorhombic(self.array)

    @property
    def ndim(self):
        return self.array.ndim

    def box(self):
        """Return cell lengths if orthorhombic, else raise ValueError."""
        # XXX More intelligent name for thos method?
        return orthorhombic(self.array)

    def __array__(self, dtype=float):
        if dtype != float:
            raise ValueError('Cannot convert cell to array of type {}'
                             .format(dtype))
        return self.array

    def __bool__(self):
        return bool(self.array.any())

    def __ne__(self, other):
        return self.array != other

    def __eq__(self, other):
        return self.array == other

    __nonzero__ = __bool__

    @property
    def volume(self):
        # Fail or 0 for <3D cells?
        # Definitely 0 since this is currently a property.
        # I think normally it is more convenient just to get zero
        return np.abs(np.linalg.det(self.array))

    def scaled_positions(self, positions):
        return np.linalg.solve(self.complete().array.T, positions.T).T

    def cartesian_positions(self, scaled_positions):
        return np.dot(scaled_positions, self.complete().array)

    def reciprocal(self):
        return np.linalg.pinv(self.array).transpose()

    def __repr__(self):
        if self.is_orthorhombic:
            numbers = self.box().tolist()
        else:
            numbers = self.tolist()

        pbc = self.pbc
        if all(pbc):
            pbc = True
        elif not any(pbc):
            pbc = False
        return 'Cell({}, pbc={})'.format(numbers, pbc)

    def niggli_reduce(self):
        from ase.build.tools import niggli_reduce_cell
        cell, _ = niggli_reduce_cell(self.array)
        return Cell(cell)

    #def bandpath(self, path, npoints=50):
    #    from ase.dft.kpoints import bandpath, BandPath
    #    objs = bandpath(path, self.array, npoints=npoints)
    #    return BandPath(*objs, names=path)

    #def special_points(self, eps=2e-4):
    #    from ase.dft.kpoints import get_special_points
    #    return get_special_points(self.array, eps=eps)

    #def special_paths(self, eps=2e-4):
    #    from ase.dft.kpoints import special_paths
    #    structure = self.crystal_structure(eps=eps)
    #    pathstring = special_paths[structure]
    #    paths = pathstring.split(',')
    #    return paths

    #def bravais_type(self, eps=2e-4):
    #    """Get bravais lattice and lattice parameters as (lattice, par).

    #    lattice, par = uc.bravais()
    #    print(uc.cellpar())
    #    print(lattice(**par).cellpar())"""
    #    return get_bravais_lattice(self, eps=eps)


def unit_vector(x):
    """Return a unit vector in the same direction as x."""
    y = np.array(x, dtype='float')
    return y / norm(y)


def angle(x, y):
    """Return the angle between vectors a and b in degrees."""
    return arccos(dot(x, y) / (norm(x) * norm(y))) * 180. / pi


def cell_to_cellpar(cell, radians=False):
    """Returns the cell parameters [a, b, c, alpha, beta, gamma].

    Angles are in degrees unless radian=True is used.
    """
    lengths = [np.linalg.norm(v) for v in cell]
    angles = []
    for i in range(3):
        j = i - 1
        k = i - 2
        ll = lengths[j] * lengths[k]
        if ll > 1e-16:
            x = np.dot(cell[j], cell[k]) / ll
            angle = 180.0 / pi * arccos(x)
        else:
            angle = 90.0
        angles.append(angle)
    if radians:
        angles = [angle * pi / 180 for angle in angles]
    return np.array(lengths + angles)


def cellpar_to_cell(cellpar, ab_normal=(0, 0, 1), a_direction=None):
    """Return a 3x3 cell matrix from cellpar=[a,b,c,alpha,beta,gamma].

    Angles must be in degrees.

    The returned cell is orientated such that a and b
    are normal to `ab_normal` and a is parallel to the projection of
    `a_direction` in the a-b plane.

    Default `a_direction` is (1,0,0), unless this is parallel to
    `ab_normal`, in which case default `a_direction` is (0,0,1).

    The returned cell has the vectors va, vb and vc along the rows. The
    cell will be oriented such that va and vb are normal to `ab_normal`
    and va will be along the projection of `a_direction` onto the a-b
    plane.

    Example:

    >>> cell = cellpar_to_cell([1, 2, 4, 10, 20, 30], (0, 1, 1), (1, 2, 3))
    >>> np.round(cell, 3)
    array([[ 0.816, -0.408,  0.408],
           [ 1.992, -0.13 ,  0.13 ],
           [ 3.859, -0.745,  0.745]])

    """
    if a_direction is None:
        if np.linalg.norm(np.cross(ab_normal, (1, 0, 0))) < 1e-5:
            a_direction = (0, 0, 1)
        else:
            a_direction = (1, 0, 0)

    # Define rotated X,Y,Z-system, with Z along ab_normal and X along
    # the projection of a_direction onto the normal plane of Z.
    ad = np.array(a_direction)
    Z = unit_vector(ab_normal)
    X = unit_vector(ad - dot(ad, Z) * Z)
    Y = np.cross(Z, X)

    # Express va, vb and vc in the X,Y,Z-system
    alpha, beta, gamma = 90., 90., 90.
    if isinstance(cellpar, (int, float)):
        a = b = c = cellpar
    elif len(cellpar) == 1:
        a = b = c = cellpar[0]
    elif len(cellpar) == 3:
        a, b, c = cellpar
    else:
        a, b, c, alpha, beta, gamma = cellpar

    # Handle orthorhombic cells separately to avoid rounding errors
    eps = 2 * np.spacing(90.0, dtype=np.float64)  # around 1.4e-14
    # alpha
    if abs(abs(alpha) - 90) < eps:
        cos_alpha = 0.0
    else:
        cos_alpha = cos(alpha * pi / 180.0)
    # beta
    if abs(abs(beta) - 90) < eps:
        cos_beta = 0.0
    else:
        cos_beta = cos(beta * pi / 180.0)
    # gamma
    if abs(gamma - 90) < eps:
        cos_gamma = 0.0
        sin_gamma = 1.0
    elif abs(gamma + 90) < eps:
        cos_gamma = 0.0
        sin_gamma = -1.0
    else:
        cos_gamma = cos(gamma * pi / 180.0)
        sin_gamma = sin(gamma * pi / 180.0)

    # Build the cell vectors
    va = a * np.array([1, 0, 0])
    vb = b * np.array([cos_gamma, sin_gamma, 0])
    cx = cos_beta
    cy = (cos_alpha - cos_beta * cos_gamma) / sin_gamma
    cz = sqrt(1. - cx * cx - cy * cy)
    vc = c * np.array([cx, cy, cz])

    # Convert to the Cartesian x,y,z-system
    abc = np.vstack((va, vb, vc))
    T = np.vstack((X, Y, Z))
    cell = dot(abc, T)

    return cell


def metric_from_cell(cell):
    """Calculates the metric matrix from cell, which is given in the
    Cartesian system."""
    cell = np.asarray(cell, dtype=float)
    return np.dot(cell, cell.T)


class Bravais:
    data = dict(cub='cubic',
                fcc='face-centered cubic',
                bcc='body-centered cubic',
                tet='tetragonal',
                bct='body-centered tetragonal',
                orc='orthorhombic',
                orcf='face-centered orthorhombic',
                orci='body-centered orthorhombic',
                orcc='c-centered orthorhombic',
                hex='hexagonal',
                rhl='rhombohedral',
                mcl='monoclinic',
                mclc='c-centered monoclinic',
                tri='triclinic')

    def __init__(self, newcellarray):
        self.newcellarray = newcellarray

    @property
    def type(self):
        """Short name, e.g. fcc."""
        return self.newcellarray.__name__

    @property
    def name(self):
        """Long name, e.g. face-centered cubic"""
        return self.data[self.type]

    @property
    def varnames(self):
        """Get names of standardized variables that define cell."""
        # The varnames are the standardized arguments that define a
        # lattice, e.g. ['a', 'c'] for tetragonal.  We might as well
        # take them from the function which builds the lattice:
        code = self.newcellarray.__code__
        return code.co_varnames[:code.co_argcount]

    def __call__(self, *args, **kwargs):
        """Return a new cell.

        Allowed arguments are those given by varnames."""
        cycle = kwargs.pop('cycle', None)
        cell = self.newcellarray(*args, **kwargs)
        assert cell.shape == (3, 3), cell
        if cycle:
            perm = (np.arange(-3, 0) + cycle) % 3
            cell = cell[perm]
        return Cell(cell)

    def __repr__(self):
        return '{}({}{})'.format(self.__class__.__name__,
                                 self.type,
                                 self.varnames)


bravais = {}
def bravaisclass(func):
    name = func.__name__
    b = Bravais(func)
    bravais[name] = b
    return b


@bravaisclass
def cub(a):
    return a * np.eye(3)

@bravaisclass
def fcc(a):
    return 0.5 * np.array([[0., a, a], [a, 0, a], [a, a, 0]])

@bravaisclass
def bcc(a):
    return 0.5 * np.array([[-a, a, a], [a, -a, a], [a, a, -a]])

@bravaisclass
def tet(a, c):
    return np.diag(np.array([a, a, c]))

@bravaisclass
def bct(a, c):
    return 0.5 * np.array([[-a, a, c], [a, -a, c], [a, a, -c]])

@bravaisclass
def orc(a, b, c):
    return np.diag([a, b, c]).astype(float)

@bravaisclass
def orcf(a, b, c):
    return 0.5 * np.array([[0, b, c], [a, 0, c], [a, b, 0]])

@bravaisclass
def orci(a, b, c):
    return 0.5 * np.array([[-a, b, c], [a, -b, c], [a, b, -c]])

@bravaisclass
def orcc(a, b, c):
    return np.array([[0.5 * a, -0.5 * b, 0], [0.5 * a, 0.5 * b, 0], [0, 0, c]])

@bravaisclass
def hex(a, c):
    x = 0.5 * np.sqrt(3)
    return np.array([[0.5 * a, -x * a, 0], [0.5 * a, x * a, 0], [0., 0., c]])

@bravaisclass
def rhl(a, alpha):
    alpha *= np.pi / 180
    acosa = a * np.cos(alpha)
    acosa2 = a * np.cos(0.5 * alpha)
    asina2 = a * np.sin(0.5 * alpha)
    acosfrac = acosa / acosa2
    return np.array([[acosa2, -asina2, 0], [acosa2, asina2, 0],
                     [a * acosfrac, 0, a * np.sqrt(1 - acosfrac**2)]])

@bravaisclass
def mcl(a, b, c, alpha):
    alpha *= np.pi / 180
    return np.array([[a, 0, 0], [0, b, 0],
                     [0, c * np.cos(alpha), c * np.sin(alpha)]])

@bravaisclass
def mclc(a, b, c, alpha):
    alpha *= np.pi / 180
    return np.array([[0.5 * a, 0.5 * b, 0], [-0.5 * a, 0.5 * b, 0],
                     [0, c * np.cos(alpha), c * np.sin(alpha)]])

@bravaisclass
def tri(a, b, c, alpha, beta, gamma):
    alpha, beta, gamma = np.array([alpha, beta, gamma]) * (np.pi / 180)
    singamma = np.sin(gamma)
    cosgamma = np.cos(gamma)
    cosbeta = np.cos(beta)
    cosalpha = np.cos(alpha)
    a3x = c * cosbeta
    a3y = c / singamma * (cosalpha - cosbeta * cosgamma)
    a3z = c / singamma * np.sqrt(singamma**2 - cosalpha**2 - cosbeta**2
                                 + 2 * cosalpha * cosbeta * cosgamma)
    return np.array([[a, 0, 0], [b * cosgamma, b * singamma, 0],
                     [a3x, a3y, a3z]])


def crystal_structure_from_cell(cell, eps=2e-4, niggli_reduce=True):
    """Return the crystal structure as a string calculated from the cell.

    Supply a cell (from atoms.get_cell()) and get a string representing
    the crystal structure returned. Works exactly the opposite
    way as ase.dft.kpoints.get_special_points().

    Parameters:

    cell : numpy.array or list
        An array like atoms.get_cell()

    Returns:

    crystal structure : str
        'cubic', 'fcc', 'bcc', 'tetragonal', 'orthorhombic',
        'hexagonal' or 'monoclinic'
    """
    cellpar = cell_to_cellpar(cell)
    abc = cellpar[:3]
    angles = cellpar[3:] / 180 * pi
    a, b, c = abc
    alpha, beta, gamma = angles

    if abc.ptp() < eps and abs(angles - pi / 2).max() < eps:
        return 'cubic'
    elif abc.ptp() < eps and abs(angles - pi / 3).max() < eps:
        return 'fcc'
    elif abc.ptp() < eps and abs(angles - np.arccos(-1 / 3)).max() < eps:
        return 'bcc'
    elif abs(a - b) < eps and abs(angles - pi / 2).max() < eps:
        return 'tetragonal'
    elif abs(angles - pi / 2).max() < eps:
        return 'orthorhombic'
    elif (abs(a - b) < eps and
          (abs(gamma - pi / 3 * 2) < eps or abs(gamma - pi / 3) < eps) and
          abs(angles[:2] - pi / 2).max() < eps):
        return 'hexagonal'
    elif (abs(angles - pi / 2) > eps).sum() == 1:
        return 'monoclinic'
    elif (abc.ptp() < eps and angles.ptp() < eps and
          np.abs(angles).max() < pi / 2):
        return 'rhombohedral type 1'
    elif (abc.ptp() < eps and angles.ptp() < eps and
          np.abs(angles).max() > pi / 2):
        return 'rhombohedral type 2'
    else:
        if niggli_reduce:
            from ase.build.tools import niggli_reduce_cell
            cell, _ = niggli_reduce_cell(cell)
            return crystal_structure_from_cell(cell, niggli_reduce=False)
        raise ValueError('Cannot find crystal structure')


def complete_cell(cell):
    """Calculate complete cell with missing lattice vectors.

    Returns a new 3x3 ndarray.
    """

    cell = np.array(cell, dtype=float)
    missing = np.nonzero(~cell.any(axis=1))[0]

    if len(missing) == 3:
        cell.flat[::4] = 1.0
    if len(missing) == 2:
        # Must decide two vectors:
        i = 3 - missing.sum()
        assert abs(cell[i, missing]).max() < 1e-16, "Don't do that"
        cell[missing, missing] = 1.0
    elif len(missing) == 1:
        i = missing[0]
        cell[i] = np.cross(cell[i - 2], cell[i - 1])
        cell[i] /= np.linalg.norm(cell[i])

    return cell


def is_orthorhombic(cell):
    """Check that cell only has stuff in the diagonal."""
    return not (np.flatnonzero(cell) % 4).any()


def orthorhombic(cell):
    """Return cell as three box dimensions or raise ValueError."""
    if not is_orthorhombic(cell):
        raise ValueError('Not orthorhombic')
    return cell.diagonal().copy()



def get_bravais_lattice(uc, eps=2e-4):
    if np.linalg.det(uc.array) < 0:
        raise ValueError('Cell should be right-handed')

    cellpar = uc.cellpar()
    ABC = cellpar[:3]
    angles = cellpar[3:]
    A, B, C, alpha, beta, gamma = cellpar

    def categorize_differences(numbers):
        a, b, c = numbers
        eq = [abs(b - c) < eps, abs(c - a) < eps, abs(a - b) < eps]
        neq = sum(eq)

        all_equal = neq == 3
        all_different = neq == 0
        funny_direction = np.argmax(eq) if neq == 1 else None
        assert neq != 2
        return all_equal, all_different, funny_direction

    (all_lengths_equal, all_lengths_different,
     unequal_length_dir) = categorize_differences(ABC)

    (all_angles_equal, all_angles_different,
     unequal_angle_dir) = categorize_differences(angles)

    def check(f, *args, **kwargs):
        axis = kwargs.pop('axis', 0)
        cell = f(*args, **kwargs)
        mycellpar = Cell(cell).cellpar()
        permutation = (np.arange(-3, 0) + axis) % 3
        mycellpar = mycellpar.reshape(2, 3)[:, permutation].ravel()
        if np.allclose(mycellpar, cellpar):
            # Return bravais function as well as the bravais parameters
            # that would reproduce the cell
            d = dict(zip(f.varnames, args))
            if axis:
                d['cycle'] = axis
            return f, d

    _c = uc.array
    BC_CA_AB = np.array([np.vdot(_c[1], _c[2]),
                         np.vdot(_c[2], _c[0]),
                         np.vdot(_c[0], _c[1])])

    _, _, unequal_scalarprod_dir = categorize_differences(BC_CA_AB)

    def allclose(a, b):
        return np.allclose(a, b, atol=eps)

    if all_lengths_equal:
        if allclose(angles, 90):
            return check(cub, A)
        if allclose(angles, 60):
            return check(fcc, np.sqrt(2) * A)
        if allclose(angles, np.arccos(-1 / 3) * 180 / np.pi):
            return check(bcc, 2.0 * A / np.sqrt(3))

    if all_lengths_equal and unequal_angle_dir is not None:
        x = BC_CA_AB[unequal_angle_dir]
        y = BC_CA_AB[(unequal_angle_dir + 1) % 3]

        if x < 0:
            c = 2.0 * np.sqrt(-y)
            a = np.sqrt(2.0 * A**2 - 0.5 * c**2)
            obj = check(bct, a, c, axis=-unequal_angle_dir + 2)
            if obj:
                return obj

    if (unequal_angle_dir is not None
          and abs(angles[unequal_angle_dir] - 120) < eps
          and abs(angles[unequal_angle_dir - 1] - 90) < eps):
        a2 = -2 * BC_CA_AB[unequal_scalarprod_dir]
        c = ABC[unequal_scalarprod_dir]
        assert a2 > 0
        return check(hex, np.sqrt(a2), c, axis=-unequal_scalarprod_dir + 2)

    if allclose(angles, 90) and unequal_length_dir is not None:
        a = ABC[unequal_length_dir - 1]
        c = ABC[unequal_length_dir]
        return check(tet, a, c, axis=-unequal_length_dir + 2)

    if unequal_length_dir is not None:
        X = ABC[unequal_length_dir - 1]**2
        Y = BC_CA_AB[unequal_length_dir]
        c = ABC[unequal_length_dir]
        a = np.sqrt(2 * (X + Y))
        b = np.sqrt(2 * (X - Y))
        obj = check(orcc, a, b, c, axis=2 - unequal_length_dir)
        if obj:
            return obj

    if allclose(angles, 90) and all_lengths_different:
        return check(orc, A, B, C)

    if all_lengths_different:
        obj = check(orcf, *(2 * np.sqrt(BC_CA_AB)))
        if obj:
            return obj

    if all_lengths_equal:
        dims2 = -2 * np.array([BC_CA_AB[1] + BC_CA_AB[2],
                               BC_CA_AB[2] + BC_CA_AB[0],
                               BC_CA_AB[0] + BC_CA_AB[1]])
        if all(dims2 > 0):
            dims = np.sqrt(dims2)
            obj = check(orci, *dims)
            if obj:
                return obj

    if all_lengths_equal:
        cosa = BC_CA_AB[0] / A**2
        alpha = np.arccos(cosa) * 180 / np.pi
        obj = check(rhl, A, alpha)
        if obj:
            return obj

    if all_lengths_different and unequal_scalarprod_dir is not None:
        alpha = angles[unequal_scalarprod_dir]
        abc = ABC[np.arange(-3, 0) + unequal_scalarprod_dir]
        obj = check(mcl, *abc, alpha=alpha, axis=-unequal_scalarprod_dir)
        if obj:
            return obj

    if unequal_length_dir is not None:
        c = ABC[unequal_length_dir]
        L = ABC[unequal_length_dir - 1]
        b = np.sqrt(2 * (L**2 + BC_CA_AB[unequal_length_dir]))
        a = np.sqrt(4 * L**2 - b**2)
        cosa = 2 * BC_CA_AB[unequal_length_dir - 1] / (b * c)
        alpha = np.arccos(cosa) * 180 / np.pi
        obj = check(mclc, a, b, c, alpha, axis=-unequal_length_dir + 2)
        if obj:
            return obj

    obj = check(tri, A, B, C, *angles)
    if obj:
        # Should always be true
        return obj

    raise RuntimeError('Cannot recognize cell at all somehow!')
