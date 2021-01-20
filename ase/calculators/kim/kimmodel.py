"""
ASE Calculator for interatomic models compatible with the Knowledgebase
of Interatomic Models (KIM) application programming interface (API).
Written by:

Mingjian Wen
Daniel S. Karls
University of Minnesota
"""
import numpy as np

from ase.calculators.calculator import Calculator
from ase.calculators.calculator import compare_atoms

from . import kimpy_wrappers
from . import neighborlist

class KIMModelData:
    """Initializes and subsequently stores the KIM API Portable Model
    object, KIM API ComputeArguments object, and the neighbor list
    object used by instances of KIMModelCalculator.  Also stores the
    arrays which are registered in the KIM API and which are used to
    communicate with the model.
    """

    def __init__(self, model_name, ase_neigh, neigh_skin_ratio, debug=False):
        self.model_name = model_name
        self.ase_neigh = ase_neigh
        self.debug = debug

        # Initialize KIM API Portable Model object and ComputeArguments object
        self.init_kim()

        # Set cutoff
        model_influence_dist = self.kim_model.get_influence_distance()
        model_cutoffs, padding_not_require_neigh = (
            self.kim_model.get_neighbor_list_cutoffs_and_hints()
        )

        self.species_map = self.create_species_map()

        # Initialize neighbor list object
        self.init_neigh(
            neigh_skin_ratio,
            model_influence_dist,
            model_cutoffs,
            padding_not_require_neigh,
        )

    def __del__(self):
        self.clean()

    def init_kim(self):
        """Create the KIM API Portable Model object and KIM API ComputeArguments
        object
        """
        if self.kim_initialized:
            return

        self.kim_model = kimpy_wrappers.PortableModel(self.model_name, self.debug)

        # KIM API model object is what actually creates/destroys the ComputeArguments
        # object, so we must pass it as a parameter
        self.compute_args = self.kim_model.compute_arguments_create()

    def init_neigh(
        self,
        neigh_skin_ratio,
        model_influence_dist,
        model_cutoffs,
        padding_not_require_neigh,
    ):
        """Initialize neighbor list, either an ASE-native neighborlist
        or one created using the neighlist module in kimpy
        """
        neigh_list_object_type = (
            neighborlist.ASENeighborList
            if self.ase_neigh
            else neighborlist.KimpyNeighborList
        )
        self.neigh = neigh_list_object_type(
            self.compute_args,
            neigh_skin_ratio,
            model_influence_dist,
            model_cutoffs,
            padding_not_require_neigh,
            self.debug,
        )

    def update_compute_args_pointers(self, energy, forces):
        self.compute_args.update(
            self.num_particles,
            self.species_code,
            self.particle_contributing,
            self.coords,
            energy,
            forces,
        )

    def create_species_map(self):
        """Get all the supported species of the KIM model and the
        corresponding integer codes used by the model

        Returns
        -------
        species_map : dict
            key : str
                chemical symbols (e.g. "Ar")
            value : int
                species integer code (e.g. 1)
        """
        supported_species, codes = self.get_model_supported_species_and_codes()
        species_map = dict()
        for i, spec in enumerate(supported_species):
            species_map[spec] = codes[i]
            if self.debug:
                print(
                    "Species {} is supported and its code is: {}".format(spec, codes[i])
                )

        return species_map

    def clean_neigh(self):
        """If the neighbor list method being used is the one in the
        kimpy neighlist module, deallocate its memory
        """
        if self.neigh_initialized:
            self.neigh.clean()
            del self.neigh

    def clean_kim(self):
        """Deallocate the memory allocated to the KIM API Portable Model object
        and KIM API ComputeArguments object
        """
        if self.kim_initialized:
            self.kim_model.compute_arguments_destroy(self.compute_args)
            self.kim_model.destroy()
            del self.kim_model

    def clean(self):
        """Deallocate the KIM API Portable Model object, KIM API ComputeArguments
        object, and, if applicable, the neighbor list object
        """
        self.clean_neigh()
        self.clean_kim()

    @property
    def padding_image_of(self):
        return self.neigh.padding_image_of

    @property
    def num_particles(self):
        return self.neigh.num_particles

    @property
    def coords(self):
        return self.neigh.coords

    @property
    def particle_contributing(self):
        return self.neigh.particle_contributing

    @property
    def species_code(self):
        return self.neigh.species_code

    @property
    def kim_initialized(self):
        return hasattr(self, "kim_model")

    @property
    def neigh_initialized(self):
        return hasattr(self, "neigh")

    @property
    def get_model_supported_species_and_codes(self):
        return self.kim_model.get_model_supported_species_and_codes


class KIMModelCalculator(Calculator):
    """Calculator that works with KIM Portable Models (PMs).

    Calculator that carries out direct communication between ASE and a
    KIM Portable Model (PM) through the kimpy library (which provides a
    set of python bindings to the KIM API).

    Parameters
    ----------
    model_name : str
      The unique identifier assigned to the interatomic model (for
      details, see https://openkim.org/doc/schema/kim-ids)

    ase_neigh : bool, optional
      False (default): Use kimpy's neighbor list library

      True: Use ASE's internal neighbor list mechanism (usually slower
      than the kimpy neighlist library)

    neigh_skin_ratio : float, optional
      Used to determine the neighbor list cutoff distance, r_neigh,
      through the relation r_neigh = (1 + neigh_skin_ratio) * rcut,
      where rcut is the model's influence distance. (Default: 0.2)

    release_GIL : bool, optional
      Whether to release python GIL.  Releasing the GIL allows a KIM
      model to run with multiple concurrent threads. (Default: False)

    debug : bool, optional
      If True, detailed information is printed to stdout. (Default:
      False)
    """

    implemented_properties = ["energy", "forces", "stress"]

    def __init__(
        self,
        model_name,
        ase_neigh=False,
        neigh_skin_ratio=0.2,
        release_GIL=False,
        debug=False,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.model_name = model_name
        self.release_GIL = release_GIL
        self.debug = debug

        if neigh_skin_ratio < 0:
            raise ValueError('Argument "neigh_skin_ratio" must be non-negative')

        # Model output
        self.energy = None
        self.forces = None

        # Create KIMModelData object. This will take care of creating and storing the KIM
        # API Portable Model object, KIM API ComputeArguments object, and the neighbor
        # list object that our calculator needs
        self.kimmodeldata = KIMModelData(
            self.model_name, ase_neigh, neigh_skin_ratio, self.debug
        )

        self._parameters_changed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, value, traceback):
        # Explicitly deallocate all three objects held by the KIMModelData
        # instance referenced by our calculator
        self.kimmodeldata.clean()

    def __repr__(self):
        return "KIMModelCalculator(model_name={})".format(self.model_name)

    def calculate(
        self,
        atoms=None,
        properties=["energy", "forces", "stress"],
        system_changes=["positions", "numbers", "cell", "pbc"],
    ):
        """
        Inherited method from the ase Calculator class that is called by
        get_property()

        Parameters
        ----------
        atoms : Atoms
            Atoms object whose properties are desired

        properties : list of str
            List of what needs to be calculated.  Can be any combination
            of 'energy', 'forces' and 'stress'.

        system_changes : list of str
            List of what has changed since last calculation.  Can be any
            combination of these six: 'positions', 'numbers', 'cell',
            and 'pbc'.
        """

        if self._parameters_changed:
            system_changes.append('calculator')
            self._parameters_changed = False

        if system_changes:
            if self.need_neigh_update(atoms, system_changes):
                self.update_neigh(atoms, self.species_map)
                self.energy = np.array([0.0], dtype=np.double)
                self.forces = np.zeros([self.num_particles[0], 3], dtype=np.double)
                self.update_compute_args_pointers(self.energy, self.forces)
            else:
                self.update_kim_coords(atoms)

            self.kim_model.compute(self.compute_args, self.release_GIL)

        energy = self.energy[0]
        forces = self.assemble_padding_forces()

        try:
            volume = atoms.get_volume()
            stress = self.compute_virial_stress(self.forces, self.coords, volume)
        except ValueError:  # Volume cannot be computed
            stress = None

        # Quantities passed back to ASE
        self.results["energy"] = energy
        self.results["free_energy"] = energy
        self.results["forces"] = forces
        self.results["stress"] = stress

    def check_state(self, atoms, tol=1e-15):
        return compare_atoms(self.atoms, atoms, excluded_properties={'initial_charges',
            'initial_magmoms'})

    def assemble_padding_forces(self):
        """
        Assemble forces on padding atoms back to contributing atoms.

        Parameters
        ----------
        forces : 2D array of doubles
            Forces on both contributing and padding atoms

        num_contrib:  int
            Number of contributing atoms

        padding_image_of : 1D array of int
            Atom number, of which the padding atom is an image


        Returns
        -------
            Total forces on contributing atoms.
        """

        total_forces = np.array(self.forces[: self.num_contributing_particles])

        if self.padding_image_of.size != 0:
            pad_forces = self.forces[self.num_contributing_particles :]
            for f, org_index in zip(pad_forces, self.padding_image_of):
                total_forces[org_index] += f

        return total_forces

    @staticmethod
    def compute_virial_stress(forces, coords, volume):
        """Compute the virial stress in Voigt notation.

        Parameters
        ----------
        forces : 2D array
            Partial forces on all atoms (padding included)

        coords : 2D array
            Coordinates of all atoms (padding included)

        volume : float
            Volume of cell

        Returns
        -------
        stress : 1D array
            stress in Voigt order (xx, yy, zz, yz, xz, xy)
        """
        stress = np.zeros(6)
        stress[0] = -np.dot(forces[:, 0], coords[:, 0]) / volume
        stress[1] = -np.dot(forces[:, 1], coords[:, 1]) / volume
        stress[2] = -np.dot(forces[:, 2], coords[:, 2]) / volume
        stress[3] = -np.dot(forces[:, 1], coords[:, 2]) / volume
        stress[4] = -np.dot(forces[:, 0], coords[:, 2]) / volume
        stress[5] = -np.dot(forces[:, 0], coords[:, 1]) / volume

        return stress

    def get_model_supported_species_and_codes(self):
        return self.kimmodeldata.get_model_supported_species_and_codes

    @property
    def update_compute_args_pointers(self):
        return self.kimmodeldata.update_compute_args_pointers

    @property
    def kim_model(self):
        return self.kimmodeldata.kim_model

    @property
    def compute_args(self):
        return self.kimmodeldata.compute_args

    @property
    def num_particles(self):
        return self.kimmodeldata.num_particles

    @property
    def coords(self):
        return self.kimmodeldata.coords

    @property
    def padding_image_of(self):
        return self.kimmodeldata.padding_image_of

    @property
    def species_map(self):
        return self.kimmodeldata.species_map

    @property
    def neigh(self):
        return self.kimmodeldata.neigh

    @property
    def num_contributing_particles(self):
        return self.neigh.num_contributing_particles

    @property
    def update_kim_coords(self):
        return self.neigh.update_kim_coords

    @property
    def need_neigh_update(self):
        return self.neigh.need_neigh_update

    @property
    def update_neigh(self):
        return self.neigh.update

    @property
    def parameter_names(self):
        """Names of all parameters in the model."""
        nparams = self.kim_model.kim_model.get_number_of_parameters()
        names = []
        for ii in range(nparams):
            names.append(list(
                self._get_one_parameter_metadata(ii).keys()
            )[0]
            )
        return names

    def echo_parameter_metadata(self):
        """Print metadata of all the parameters in the model.
            name : name of a KIM portable model parameter
            dtype : data type of the parameter ('Integer' or 'Double')
            extent : length of the parameter list
            description : description of the parameter
        It will be useful to call this method before setting custom
        parameters to check the name of the parameters in the model
        and their extents.
        """
        num_params = self.kim_model.kim_model.get_number_of_parameters()
        print("#"*80)
        print(f"# Parameters' metadata for {self.model_name}")
        print("#"*80)
        print()
        for ii in range(num_params):
            name, items = list(
                self._get_one_parameter_metadata(ii).items()
            )[0]
            print(f"name : {name}")
            print(f"dtype : {items['dtype']}")
            print(f"extent : {items['extent']}")
            print(f"description : {items['description']}")
            print()

    def get_parameters(self, **kwargs):
        """Get values of parameters like
            get_parameters(name1=index_range1,
                           name2=index_range2,
                           ...)
        index_range can be an integer or a list of integers.

        This will return a dictionary containing parameters that are
        previously set in KIM calculator. Initially, this would be
        the default parameter values stored in KIM portable model.

        As an example, suppose we want to get epsilons and sigmas for
        Mo-Mo (index 4879), Mo-S (index 2006) and S-S (index 1980)
        interactions in LJ universal model. Then we would call
            calc.get_parameters('epsilons'=[4879, 2006, 1980],
                                'sigmas'=[4879, 2006, 1980])
        """
        parameters = {}
        for parameter_name, index_range in kwargs.items():
            parameters.update(
                self._get_one_parameter(
                    parameter_name, index_range
                )
            )
        return parameters

    def set_parameters(self, **kwargs):
        """Set values of parameters like
            set_parameters(name1=[index_range1, values1],
                           name2=[index_range2, values2],
                           ...)
        index_range and values can be float or integer, or list of
        floats and integers.

        This will return a dictionary containing parameters that
        are set.

        As an example, suppose we want to set epsilons for Mo-Mo
        (index 4879), Mo-S (index 2006) and S-S (index 1980)
        interactions in LJ universal model to 5.0, 4.5, and 4.0,
        respectively. Then we would call
            calc.set_parameters('epsilons'=[[4879, 2006, 1980],
                                            [5.0, 4.5, 4.0]])
        """
        parameters = {}
        for parameter_name, parameter_data in kwargs.items():
            self._set_one_parameter(
                parameter_name,
                parameter_data[0], parameter_data[1]
            )
            parameters.update(
                {parameter_name: parameter_data}
            )
        self.kim_model.kim_model.clear_then_refresh()
        self._parameters_changed = True
        return parameters

    def _get_one_parameter(self, parameter_name,
                           index_range):
        """Get values of one of the parameter."""
        # Check if model has parameter_name
        if parameter_name not in self.parameter_names:
            raise ValueError(
                f'Parameter {parameter_name} is not supported.')

        parameter_name_index = self._get_parameter_name_index(
            parameter_name
        )
        parameter_metadata = self._get_one_parameter_metadata(
            parameter_name_index
        )
        dtype = list(parameter_metadata.values())[0]['dtype']

        index_range_dim = np.ndim(index_range)
        if index_range_dim == 0:
            values = self._get_one_value(
                parameter_name_index, int(index_range), dtype
            )
        elif index_range_dim == 1:
            values = []
            for idx in index_range:
                values.append(
                    self._get_one_value(
                        parameter_name_index, int(idx), dtype
                    )
                )
        else:
            raise ValueError(
                'Index range must be an integer or a list of integer'
            )
        return {parameter_name: values}

    def _set_one_parameter(self, parameter_name,
                           index_range, values):
        """Set values of one parameter in kim calculator.
        """
        # Check if model has parameter_name
        if parameter_name not in self.parameter_names:
            raise ValueError(
                f'Parameter {parameter_name} is not supported.')

        parameter_name_index = self._get_parameter_name_index(
            parameter_name
        )
        parameter_metadata = self._get_one_parameter_metadata(
            parameter_name_index
        )
        dtype = list(parameter_metadata.values())[0]['dtype']

        index_range_dim = np.ndim(index_range)
        values_dim = np.ndim(values)

        # Check the shape of index_range and values
        msg = 'index_range and values must have the same shape'
        assert index_range_dim == values_dim, msg

        if index_range_dim == 0:
            self._set_one_value(
                parameter_name_index, index_range, dtype, values
            )
        elif index_range_dim == 1:
            assert len(index_range) == len(values), msg
            for idx, value in zip(index_range, values):
                self._set_one_value(
                    parameter_name_index, idx, dtype, value
                )
        else:
            raise ValueError(
                'Index range must be an integer or a list of integer'
            )

    def _get_one_parameter_metadata(self, index_parameter):
        """Get parameter metadata."""
        out = self.kim_model.kim_model.get_parameter_metadata(
            index_parameter
        )
        dtype, extent, name, description, error = out
        dtype = repr(dtype)
        pdata = {name: {'dtype': dtype,
                        'extent': extent,
                        'description': description,
                        'error': error}}
        return pdata

    def _get_parameter_name_index(self, parameter_name):
        """Given parameter_name, find index of parameter stored in the
        model.
        """
        parameter_name_index = np.where(
            np.asarray(self.parameter_names) == parameter_name
        )[0]
        return parameter_name_index

    def _get_one_value(self, index_param, index_extent, dtype):
        """Get values of one parameter."""
        if dtype == 'Double':
            pp = self.kim_model.kim_model.get_parameter_double(
                index_param, index_extent
            )[0]
        else:
            pp = self.kim_model.kim_model.get_parameter_int(
                index_param, index_extent
            )[0]
        return pp

    def _set_one_value(self, index_param, index_extent,
                       dtype, value):
        """Update one parameter in kim model."""
        if dtype == 'Integer':
            self.kim_model.kim_model.set_parameter(
                index_param, int(index_extent), int(value)
            )
        elif dtype == 'Double':
            self.kim_model.kim_model.set_parameter(
                index_param, int(index_extent), float(value)
            )
