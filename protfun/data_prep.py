import os
import csv
import StringIO
import numpy as np
import theano

floatX = theano.config.floatX
intX = np.int32  # FIXME is this the best choice? (changing would require removing and recreating memmap files)


class DataSetup(object):
    """
    Sets up the data set by downloading PDB proteins and doing initial processing into memmaps.
    """

    def __init__(self, foldername='data', update=True, prot_codes=None, split_test=0.1):
        """

        :param foldername: the directory that will contain the data set
        :param update: whether the data set should be updated (downloaded again & memmaps generated).
        :param prot_codes: which protein codes the dataset should contain. Only makes sense if redownload=True.
        :param split_test: ration of training vs. test data
        """

        self.data_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../", foldername)
        self.pdb_dir = os.path.join(self.data_dir, "pdb")
        self.go_dir = os.path.join(self.data_dir, "go")
        self.memmap_dir = os.path.join(self.data_dir, "moldata")

        if not os.path.exists(self.pdb_dir):
            os.makedirs(self.pdb_dir)
        if not os.path.exists(self.go_dir):
            os.makedirs(self.go_dir)
        if not os.path.exists(self.memmap_dir):
            os.makedirs(self.memmap_dir)

        self.prot_codes = prot_codes
        self.split_test = split_test
        self.pdb_files = []
        self._setup(update)

    def _setup(self, update):
        if update:
            print("INFO: Proceeding to download the Protein Data Base...")
            self._download_dataset()
            print("INFO: Creating molecule data memmap files...")
            self._preprocess_dataset()
        else:
            # checking for pdb related files
            pdb_list = [f for f in os.listdir(self.pdb_dir) if
                        f.endswith('.gz') or f.endswith('.pdb') or f.endswith('.ent')]
            if not pdb_list:
                print("WARNING: %s does not contain any PDB files. " +
                      "Run the DataSetup with update=True to download them." % self.pdb_dir)

            # checking for molecule data memmaps
            memmap_list = [f for f in os.listdir(self.memmap_dir) if f.endswith('.memmap')]
            if not memmap_list:
                print("WARNING: %s does not contain any memmap files. " +
                      "Run the DataSetup with update=True to recreate them." % self.pdb_dir)

    def _download_dataset(self):
        """
        Downloads the PDB database (or a part of it) as PDB files.
        """
        # TODO: control the number of molecules to download if the entire DB is too large
        # download the Protein Data Base
        from Bio.PDB import PDBList
        pl = PDBList(pdb=self.pdb_dir)
        pl.flat_tree = 1
        if self.prot_codes is not None:
            for code in self.prot_codes:
                pl.retrieve_pdb_file(pdb_code=code)
        else:
            pl.download_entire_pdb()

        self.pdb_files = [os.path.join(self.pdb_dir, f) for f in os.listdir(self.pdb_dir)
                          if f.endswith(".ent") or f.endswith(".pdb")]

    def _preprocess_dataset(self):
        """
        Does pre-processing of the downloaded PDB files.
        numpy.memmap's are created for molecules (from the PDB files with no errors)
        A .csv file is created with all GO (Gene Ontology) IDs for the processed molecules.
        :return:
        """

        molecule_processor = MoleculeProcessor()
        go_processor = GeneOntologyProcessor()

        molecules = list()
        go_targets = list()

        # process all PDB files
        for f in self.pdb_files:
            # process molecule from file
            mol = molecule_processor.process_molecule(f)
            if mol is None:
                print("INFO: removing PDB file %s for invalid molecule" % f)
                self.pdb_files.remove(f)
                continue

            # process gene ontology (GO) target label from file
            go_ids = go_processor.process_gene_ontologies(f)
            if go_ids is None or len(go_ids) == 0:
                print("INFO: removing PDB file %s because it has no gene ontologies associated with it." % f)
                self.pdb_files.remove(f)
                continue

            molecules.append(mol)
            go_targets.append(go_ids)

        n_atoms = np.array([mol["atoms_count"] for mol in molecules])
        max_atoms = n_atoms.max()
        molecules_count = len(molecules)

        # after pre-processing, the PDB files should match the final molecules
        assert molecules_count == len(self.pdb_files)

        # create numpy arrays for the final data
        coords = np.zeros(shape=(molecules_count, max_atoms, 3), dtype=floatX)
        charges = np.zeros(shape=(molecules_count, max_atoms), dtype=floatX)
        vdwradii = np.ones(shape=(molecules_count, max_atoms), dtype=floatX)
        atom_mask = np.zeros(shape=(molecules_count, max_atoms), dtype=floatX)

        for i, mol in enumerate(molecules):
            coords[i, 0:mol["atoms_count"]] = mol["coords"]
            charges[i, 0:mol["atoms_count"]] = mol["charges"]
            vdwradii[i, 0:mol["atoms_count"]] = mol["vdwradii"]
            atom_mask[i, 0:mol["atoms_count"]] = 1

        n_atoms = np.asarray(n_atoms, dtype=intX)

        # save the final molecules into memmap files
        def save_to_memmap(filename, data, dtype):
            tmp = np.memmap(filename, shape=data.shape, mode='w+', dtype=dtype)
            print("INFO: Saving memmap. Shape of {0} is {1}".format(filename, data.shape))
            tmp[:] = data[:]
            tmp.flush()
            del tmp

        save_to_memmap(os.path.join(self.memmap_dir, 'max_atoms.memmap'), np.asarray([max_atoms], dtype=intX),
                       dtype=intX)
        save_to_memmap(os.path.join(self.memmap_dir, 'coords.memmap'), coords, dtype=floatX)
        save_to_memmap(os.path.join(self.memmap_dir, 'charges.memmap'), charges, dtype=floatX)
        save_to_memmap(os.path.join(self.memmap_dir, 'vdwradii.memmap'), vdwradii, dtype=floatX)
        save_to_memmap(os.path.join(self.memmap_dir, 'n_atoms.memmap'), n_atoms, dtype=intX)
        save_to_memmap(os.path.join(self.memmap_dir, 'atom_mask.memmap'), atom_mask, dtype=floatX)

        # save the final GO targets into a .csv file
        with open(os.path.join(self.go_dir, "go_ids.csv"), "wb") as f:
            csv.writer(f).writerows(go_targets)

    def load_dataset(self):
        # TODO: make it work meaningfully
        data = np.random.randn(10, 10)
        labels = np.random.randn(10, 10)
        train_data_mask, test_data_mask = self._split_dataset(data)
        data_dict = {'x_train': data[train_data_mask], 'y_train': labels[train_data_mask],
                     'x_val': data[train_data_mask], 'y_val': labels[train_data_mask],
                     'x_test': data[test_data_mask], 'y_test': labels[test_data_mask]}

        print("INFO: Data loaded")
        # TODO set the num_gene_ontologies to the filtered number of different ontologies
        return data_dict

    @staticmethod
    def _split_dataset(self, data_ids=None):
        # TODO use self.split_test
        return np.random.randint(0, 10, 2), np.random.randint(0, 10, 2)


class MoleculeProcessor(object):
    """
    MoleculeProcessor can produce a ProcessedMolecule from the contents of a PDB file.
    """

    def __init__(self):
        import rdkit.Chem as Chem
        self.periodic_table = Chem.GetPeriodicTable()

    def process_molecule(self, pdb_file):
        """
        Processes a molecule from the passed PDB file if the file contents has no errors.
        :param pdb_file: path to the PDB file to process the molecule from.
        :return: a ProcessedMolecule object
        """
        import rdkit.Chem as Chem
        import rdkit.Chem.rdPartialCharges as rdPC
        import rdkit.Chem.rdMolTransforms as rdMT
        import rdkit.Chem.rdmolops as rdMO

        # read a molecule from the PDB file
        mol = Chem.MolFromPDBFile(molFileName=pdb_file, removeHs=False, sanitize=True)
        if mol is None:
            print("WARNING: Bad pdb file found.")
            return None

        # add missing hydrogen atoms
        rdMO.AddHs(mol, addCoords=True)

        # compute partial charges
        try:
            rdPC.ComputeGasteigerCharges(mol, throwOnParamFailure=True)
        except ValueError:
            print("WARNING: Bad Gasteiger charge evaluation.")
            return None

        # get the conformation of the molecule
        conformer = mol.GetConformer()

        # calculate the center of the molecule
        center = rdMT.ComputeCentroid(conformer, ignoreHs=False)

        atoms_count = mol.GetNumAtoms()
        atoms = mol.GetAtoms()

        def get_coords(i):
            coord = conformer.GetAtomPosition(i)
            return np.asarray([coord.x, coord.y, coord.z])

        # set the coordinates, charges, VDW radii and atom count
        res = {}
        res["coords"] = np.asarray(
            [get_coords(i) for i in range(0, atoms_count)]) - np.asarray(
            [center.x, center.y, center.z])

        res["charges"] = np.asarray(
            [float(atom.GetProp("_GasteigerCharge")) for atom in atoms])

        res["vdwradii"] = np.asarray([self.periodic_table.GetRvdw(atom.GetAtomicNum()) for atom in atoms])

        res["atoms_count"] = atoms_count
        return res


class GeneOntologyProcessor(object):
    """
    GeneOntologyProcessor can read a list of GO (Gene Ontology) from a PDB file.
    """

    def process_gene_ontologies(self, pdb_file):
        """
        Processes a PDB file and returns a list with GO ids that can be associated with it.
        :param pdb_file: the path to the PDB file that is to be processed.
        :return: a list of GO ids for the molecule contained in the PDB file.
        """
        from prody.proteins.header import parsePDBHeader
        import requests

        polymers = parsePDBHeader(pdb_file, "polymers")
        uniprot_ids = set()
        for polymer in polymers:
            for dbref in polymer.dbrefs:
                if dbref.database == "UniProt":
                    uniprot_ids.add(dbref.accession)

        go_ids = []
        for uniprot_id in uniprot_ids:
            url = "http://www.ebi.ac.uk/QuickGO/GAnnotation?protein=" + uniprot_id + "&format=tsv"
            response = requests.get(url)
            go_ids += self._parse_gene_ontology(response.text)

        return go_ids

    @staticmethod
    def _parse_gene_ontology(tsv_text):
        f = StringIO.StringIO(tsv_text)
        reader = csv.reader(f, dialect="excel-tab")
        # skip the header
        next(reader)
        try:
            return zip(*[line for line in reader])[6]
        except IndexError:
            # protein has no GO terms associated with it
            return ["unknown"]
