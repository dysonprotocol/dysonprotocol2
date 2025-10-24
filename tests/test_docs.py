"""
Test module for validating that all Jupyter notebooks in the notebooks directory run without errors.

This module uses nbconvert to execute notebooks programmatically and pytest to assert
that they complete successfully without raising exceptions.
"""

import os
import glob
import json
import pytest
import subprocess
import tempfile
import shutil
from pathlib import Path

# Apply docs marker to all tests in this module
pytestmark = pytest.mark.docs


class NotebookExecutionError(Exception):
    """Custom exception for notebook execution failures."""

    pass


JUPYTER_PATH = shutil.which("jupyter")
JUPYTER_EXECUTABLE = bool(JUPYTER_PATH and os.access(JUPYTER_PATH, os.X_OK))


def get_notebook_files():
    """
    Get all Jupyter notebook files from the notebooks directory.

    Returns:
        list: List of paths to .ipynb files
    """
    notebooks_dir = Path(__file__).parent.parent / "notebooks"
    notebook_files = list(notebooks_dir.glob("*.ipynb"))

    # Filter out checkpoint files
    notebook_files = [
        nb for nb in notebook_files if ".ipynb_checkpoints" not in str(nb)
    ]

    return notebook_files


def clear_notebook_outputs(notebook_path, env=None):
    """
    Clear all outputs from a Jupyter notebook.

    Args:
        notebook_path (Path): Path to the notebook file
        env (dict): Optional environment variables to use

    Returns:
        bool: True if clearing succeeded, False otherwise
    """
    cmd = ["jupyter", "nbconvert", "--clear-output", "--inplace", str(notebook_path)]

    env = env or os.environ.copy()

    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=notebook_path.parent, env=env
    )

    return result.returncode == 0


def execute_notebook(notebook_path, dyson_home, env=None):
    """
    Execute a Jupyter notebook and convert to markdown while keeping original clean.

    This function executes the notebook and outputs the results as markdown to a
    file with the same name as the notebook, then ensures the original notebook
    file remains without outputs.

    Args:
        notebook_path (Path): Path to the notebook file
        dyson_home (str): Path to the dyson home directory
        env (dict): Optional environment variables to use

    Returns:
        tuple: (success: bool, markdown_path: str, error: str)
    """
    # Ensure docs output directory exists and build output path ./docs/{name}.md
    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = docs_dir / f"{notebook_path.stem}.md"

    # Execute the notebook and convert to markdown
    cmd = [
        "jupyter",
        "nbconvert",
        "--to",
        "markdown",
        "--TagRemovePreprocessor.enabled=True",
        "--TagRemovePreprocessor.remove_input_tags",
        "hide-input",
        "--execute",
        "--output",
        notebook_path.stem,
        "--output-dir",
        str(docs_dir),
        "--ExecutePreprocessor.timeout=30",  # Increased timeout for blockchain operations
        "--ExecutePreprocessor.kernel_name=python3",
        str(notebook_path),
    ]

    print(
        f"Executing notebook to markdown: {notebook_path.name} -> {markdown_path.name}"
    )
    env = env or {}
    env.update(os.environ.copy())
    env["DYSON_HOME"] = dyson_home

    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=notebook_path.parent, env=env
    )

    success = result.returncode == 0

    # Ensure the original notebook remains clean (no outputs)
    clear_notebook_outputs(notebook_path, env)

    return success, str(markdown_path), result.stderr


def validate_notebook_structure(notebook_path):
    """
    Validate that the notebook file has valid JSON structure.

    Args:
        notebook_path (Path): Path to the notebook file

    Returns:
        bool: True if valid, False otherwise
    """
    # Load notebook data and check structure
    with open(notebook_path, "r", encoding="utf-8") as f:
        notebook_data = json.load(f)

    # Basic validation - check for required fields
    required_fields = ["cells", "metadata", "nbformat"]
    missing_fields = [field for field in required_fields if field not in notebook_data]

    return len(missing_fields) == 0


def pytest_generate_tests(metafunc):
    """
    Dynamically generate tests for each notebook file.

    This creates individual named tests for each notebook, allowing for:
    - pytest --ff (fail fast) to work properly
    - Running specific notebook tests by name
    - Better test reporting with individual notebook names
    """
    # Only parametrize if notebook_path is in the fixture names
    has_notebook_path = "notebook_path" in metafunc.fixturenames

    # Get notebook files and create parametrization if needed
    notebook_files = get_notebook_files() if has_notebook_path else []
    test_ids = [nb.stem for nb in notebook_files] if has_notebook_path else []

    # Parametrize if we have the fixture
    (
        metafunc.parametrize("notebook_path", notebook_files, ids=test_ids)
        if has_notebook_path
        else None
    )


@pytest.mark.docs
def test_notebook_structure(notebook_path):
    """
    Test that each notebook has valid JSON structure.

    Args:
        notebook_path (Path): Path to the notebook file
    """
    assert validate_notebook_structure(
        notebook_path
    ), f"Invalid notebook structure: {notebook_path}"


@pytest.mark.docs
@pytest.mark.skipif(
    not JUPYTER_EXECUTABLE,
    reason="Jupyter CLI not found or not executable; skipping docs execution tests",
)
def test_notebook_execution(notebook_path, chainnet):
    """
    Test that each notebook executes without errors.

    Args:
        notebook_path (Path): Path to the notebook file
        chainnet: Chainnet fixture providing access to test chains
        test_config_path: Path to the chainnet configuration file
    """
    # Skip execution if jupyter/nbconvert is not available
    result = subprocess.run(["jupyter", "--version"], capture_output=True)
    assert result.returncode == 0, "Jupyter not available - cannot execute notebooks"

    # Get the first chain's run command
    dysond_bin = chainnet[0]

    # Get the home directory of the first node of the first chain
    dyson_home = dysond_bin("config", "home").strip()
    print(f"Dyson home: {dyson_home}")

    # Execute the notebook with a clean env that sets DYSON_HOME; coverage vars pass through
    env = os.environ.copy()
    env["DYSON_HOME"] = dyson_home

    success, markdown_path, stderr = execute_notebook(notebook_path, dyson_home, env)

    assert (
        success
    ), f"Notebook execution failed: {notebook_path}\nMarkdown output: {markdown_path}\nSTDERR:\n{stderr}"


@pytest.mark.docs
def test_notebooks_exist():
    """Test that there are actually notebook files to test."""
    notebook_files = get_notebook_files()
    assert len(notebook_files) > 0, "No notebook files found in notebooks directory"
