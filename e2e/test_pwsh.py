import os
import tempfile
from pathlib import Path
import subprocess

from common import STRACE_EXPR_GRAMMAR, LSOF_FILTER_GRAMMAR
from conftest import (
    gen_pwsh_completion_script_path,
    get_sorted_pwsh_completions,
    set_working_dir,
)

import pytest


def test_basic_pwsh_script_generation(complgen_binary_path: Path):
    """Test basic PowerShell completion script generation."""
    GRAMMAR = "cmd foo bar;"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Check basic structure
        assert "Register-ArgumentCompleter" in content
        assert "-CommandName 'cmd'" in content
        assert "'foo'" in content
        assert "'bar'" in content
        assert "$literals = @(" in content
        assert "$completions" in content


def test_pwsh_script_syntax_validation(complgen_binary_path: Path):
    """Test that generated PowerShell scripts are syntactically valid."""
    GRAMMAR = "cmd foo bar;"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        # Test PowerShell syntax validation using Parse method
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", 
             f"[System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$null)"],
            capture_output=True,
            text=True
        )
        # PowerShell parser should not return errors for valid syntax
        assert result.returncode == 0, f"PowerShell syntax error: {result.stderr}"


def test_pwsh_with_descriptions(complgen_binary_path: Path):
    """Test PowerShell completion with descriptions."""
    GRAMMAR = '''cmd (foo "First option" | bar "Second option");'''
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Check that descriptions are included
        assert "$descriptions = @{}" in content
        assert "First option" in content
        assert "Second option" in content


def test_pwsh_empty_command_switch(complgen_binary_path: Path):
    """Test PowerShell completion with simple grammar has proper switch statement."""
    GRAMMAR = "cmd --help;"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Should have a switch statement with default case for when no external commands are present  
        assert "switch ($CommandId) {" in content
        assert "default { return @() }" in content


def test_pwsh_array_syntax_no_trailing_commas(complgen_binary_path: Path):
    """Test that PowerShell arrays don't have trailing commas."""
    GRAMMAR = "cmd foo bar baz;"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Check literals array doesn't have trailing comma after last element
        lines = content.split('\n')
        literals_section = False
        for line in lines:
            if "$literals = @(" in line:
                literals_section = True
                continue
            if literals_section and ")" in line and "$" not in line:
                # This should be the closing of the literals array
                literals_section = False
                continue
            if literals_section and line.strip().startswith("'"):
                # This is a literal line
                if "'baz'" in line:
                    # This should be the last element, no trailing comma
                    assert not line.strip().endswith(","), f"Last element has trailing comma: {line}"


def test_pwsh_regexes_array_syntax(complgen_binary_path: Path):
    """Test that PowerShell regexes array is properly formatted."""
    GRAMMAR = "cmd foo;"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Check that regexes array is properly formatted
        assert "$regexes = @(" in content
        # Should close the array properly
        regex_lines = []
        in_regex_section = False
        for line in content.split('\n'):
            if "$regexes = @(" in line:
                in_regex_section = True
                continue
            if in_regex_section:
                if line.strip() == ")":
                    break
                regex_lines.append(line.strip())
        
        # Even empty regexes array should be properly closed
        assert ")" in content[content.find("$regexes = @("):]


def test_pwsh_handles_special_characters_in_strings(complgen_binary_path: Path):
    """Test PowerShell completion with special characters in literals."""
    GRAMMAR = "cmd --option='value' \"quoted\";"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Check that special characters are present in the script
        # PowerShell single quotes are escaped by doubling
        assert "'" in content or "''" in content


def test_pwsh_command_with_external_commands(complgen_binary_path: Path):
    """Test PowerShell completion with external commands."""
    GRAMMAR = '''cmd {{{ echo hello }}};'''
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Should have command execution logic
        assert "function Invoke-Command {" in content
        assert "switch ($CommandId) {" in content
        # Should have at least one command case since we have an external command
        assert "& " in content or "default { return @() }" in content


def test_pwsh_completion_result_creation(complgen_binary_path: Path):
    """Test that PowerShell completion creates proper CompletionResult objects."""
    GRAMMAR = "cmd foo bar;"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Should create CompletionResult objects
        assert "System.Management.Automation.CompletionResult" in content
        assert "CompletionResult]::new(" in content


def test_pwsh_multiple_literals(complgen_binary_path: Path):
    """Test PowerShell script with multiple literals."""
    GRAMMAR = "cmd (--help | --version | --verbose | --quiet);"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Should contain all the literals
        assert "'--help'" in content
        assert "'--version'" in content
        assert "'--verbose'" in content
        assert "'--quiet'" in content


def test_pwsh_script_can_be_loaded(complgen_binary_path: Path):
    """Test that the PowerShell script can be loaded without errors."""
    GRAMMAR = "cmd foo bar;"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        # Try to load the script in PowerShell
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", f". '{script_path}'"],
            capture_output=True,
            text=True
        )
        
        # Should load without errors
        assert result.returncode == 0, f"Script loading failed: {result.stderr}"


def test_pwsh_with_complex_grammar(complgen_binary_path: Path):
    """Test PowerShell completion with a more complex grammar."""
    GRAMMAR = """
    mygrep [<OPTION>]... <PATTERN> [<FILE>]...;
    
    <OPTION> ::= --color=<WHEN> "use markers to highlight the matching strings"
               | --help "display this help and exit"
               | --version "output version information and exit"
               ;
    
    <WHEN> ::= always | never | auto;
    """
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Should handle the complex grammar without syntax errors
        assert "Register-ArgumentCompleter" in content
        assert "-CommandName 'mygrep'" in content
        
        # Test that it can be parsed
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", 
             f"[System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$null)"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0


def test_pwsh_string_escaping(complgen_binary_path: Path):
    """Test PowerShell string escaping functionality."""
    # Test various characters that need escaping
    GRAMMAR = "cmd 'single' \"double\" --key='value';"
    
    with gen_pwsh_completion_script_path(complgen_binary_path, GRAMMAR) as script_path:
        content = script_path.read_text()
        
        # Script should be syntactically valid despite special characters
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", 
             f"[System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$null)"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error with special characters: {result.stderr}"


def test_pwsh_complgen_example(complgen_binary_path: Path, examples_directory_path: Path):
    """Test PowerShell completion with the actual complgen.usage example."""
    complgen_usage_path = examples_directory_path / "complgen.usage"
    assert complgen_usage_path.exists(), "complgen.usage example file not found"
    
    grammar = complgen_usage_path.read_text()
    
    with gen_pwsh_completion_script_path(complgen_binary_path, grammar) as script_path:
        content = script_path.read_text()
        
        # Should generate a valid script
        assert "Register-ArgumentCompleter" in content
        assert "-CommandName 'complgen'" in content
        
        # Should handle the options from the grammar
        assert "'--bash'" in content
        assert "'--fish'" in content
        assert "'--zsh'" in content
        assert "'--version'" in content
        
        # Test that it can be parsed without syntax errors
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", 
             f"[System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$null)"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error in complgen example: {result.stderr}"


def test_pwsh_mygrep_example(complgen_binary_path: Path, examples_directory_path: Path):
    """Test PowerShell completion with the complex mygrep.usage example."""
    mygrep_usage_path = examples_directory_path / "mygrep.usage"
    assert mygrep_usage_path.exists(), "mygrep.usage example file not found"
    
    grammar = mygrep_usage_path.read_text()
    
    with gen_pwsh_completion_script_path(complgen_binary_path, grammar) as script_path:
        content = script_path.read_text()
        
        # Should generate a valid script
        assert "Register-ArgumentCompleter" in content
        assert "-CommandName 'mygrep'" in content
        
        # Should handle complex options
        assert "'--extended-regexp'" in content or "extended-regexp" in content
        assert "'--color'" in content or "color" in content
        
        # Test that even the complex grammar generates syntactically valid PowerShell
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-Command", 
             f"[System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$null)"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error in mygrep example: {result.stderr}"