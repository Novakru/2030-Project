import os
import pytest
from xdl import XDL
from .utils import test_snapshot

HERE = os.path.abspath(os.path.dirname(__file__))
TEST_FOLDER = os.path.dirname(HERE)
UNIT_TEST_FILES = os.path.join(TEST_FOLDER, 'unit', 'files')

@pytest.mark.snapshot
def test_snapshot_lidocaine_two_stage():
    lidocaine_xdl = os.path.join(UNIT_TEST_FILES, 'lidocaine.xdl')
    lidocaine_graph = os.path.join(UNIT_TEST_FILES, 'lidocaine_graph.json')
    process_save_path = os.path.join(UNIT_TEST_FILES, 'lidocaine-process.xdl')
    xdlexe_save_path = process_save_path + 'exe'

    x = XDL(lidocaine_xdl)
    x.executor.add_process_steps(
        lidocaine_graph,
        interactive=False,
        save_path=process_save_path,
    )

    process_xdl = XDL(process_save_path)
    for step in process_xdl.steps:
        print(step.name, step.properties, '\n')
    process_xdl.executor.optimize_and_compile(
        lidocaine_graph,
        save_path=xdlexe_save_path,
    )

    final_xdlexe = XDL(xdlexe_save_path)

    test_snapshot('lidocaine', final_xdlexe)

@pytest.mark.snapshot
def test_snapshot_lidocaine():
    lidocaine_xdl = os.path.join(UNIT_TEST_FILES, 'lidocaine.xdl')
    lidocaine_graph = os.path.join(
        UNIT_TEST_FILES, 'lidocaine_graph.json')
    x = XDL(lidocaine_xdl)
    x.prepare_for_execution(lidocaine_graph, interactive=False)
    test_snapshot('lidocaine', x)

@pytest.mark.snapshot
def test_snapshot_orgsyn_v81p0262():
    orgsyn_v81p0262_xdl = os.path.join(UNIT_TEST_FILES, 'orgsyn_v81p0262.xdl')
    orgsyn_v81p0262_graph = os.path.join(
        UNIT_TEST_FILES, 'orgsyn_v81p0262.json')
    x = XDL(orgsyn_v81p0262_xdl)
    x.prepare_for_execution(orgsyn_v81p0262_graph, interactive=False)
    test_snapshot('orgsyn_v81p0262', x)

@pytest.mark.snapshot
def test_snapshot_orgsyn_v81p0262_two_stage():
    orgsyn_v81p0262_xdl = os.path.join(
        UNIT_TEST_FILES, 'orgsyn_v81p0262.xdl')
    orgsyn_v81p0262_graph = os.path.join(
        UNIT_TEST_FILES, 'orgsyn_v81p0262.json')
    process_save_path = os.path.join(
        UNIT_TEST_FILES, 'orgsyn_v81p0262-process.xdl')
    xdlexe_save_path = process_save_path + 'exe'

    x = XDL(orgsyn_v81p0262_xdl)
    x.executor.add_process_steps(
        orgsyn_v81p0262_graph,
        interactive=False,
        save_path=process_save_path,
    )

    process_xdl = XDL(process_save_path)
    process_xdl.executor.optimize_and_compile(
        orgsyn_v81p0262_graph,
        save_path=xdlexe_save_path,
    )

    final_xdlexe = XDL(xdlexe_save_path)

    test_snapshot('orgsyn_v81p0262', final_xdlexe)
