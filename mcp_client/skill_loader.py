"""
Agent Skills loader.

Loads skill definitions from skills directory; provides system prompt additions, planning prompt, etc.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SkillConfig:
    """Configuration for a single skill."""

    name: str
    description: str
    directory: str
    trigger_keywords: List[str] = field(default_factory=list)
    system_additions_file: Optional[str] = None
    planning_prompt_file: Optional[str] = None

    def get_system_additions(self) -> str:
        """Read and return system prompt additions; empty string if missing."""
        if not self.system_additions_file:
            return ""
        path = os.path.join(self.directory, self.system_additions_file)
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""

    def get_planning_prompt(self) -> Optional[str]:
        """Read and return planning prompt; None if missing."""
        if not self.planning_prompt_file:
            return None
        path = os.path.join(self.directory, self.planning_prompt_file)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else None
        except Exception:
            return None


def _parse_skill_yaml(dir_path: str, name: str) -> Optional[SkillConfig]:
    """Parse skill config from skill.yaml."""
    yaml_path = os.path.join(dir_path, "skill.yaml")
    if not os.path.isfile(yaml_path):
        return None

    try:
        import yaml
    except ImportError:
        return _parse_skill_yaml_simple(dir_path, name, yaml_path)

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return None

    return SkillConfig(
        name=data.get("name", name),
        description=data.get("description", ""),
        directory=dir_path,
        trigger_keywords=data.get("trigger_keywords", []),
        system_additions_file=data.get("system_additions_file"),
        planning_prompt_file=data.get("planning_prompt_file"),
    )


def _parse_skill_yaml_simple(dir_path: str, name: str, yaml_path: str) -> Optional[SkillConfig]:
    """Simple parser when PyYAML is not available (basic key: value only)."""
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    data = {}
    for line in content.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            key = key.strip().lower().replace("-", "_")
            val = val.strip().strip("'\"")
            if key == "trigger_keywords" and val.startswith("["):
                data[key] = [x.strip().strip("'\"") for x in val[1:-1].split(",")]
            else:
                data[key] = val

    return SkillConfig(
        name=data.get("name", name),
        description=data.get("description", ""),
        directory=dir_path,
        trigger_keywords=data.get("trigger_keywords", []),
        system_additions_file=data.get("system_additions_file"),
        planning_prompt_file=data.get("planning_prompt_file"),
    )


def load_skills(skills_directory: str) -> Dict[str, SkillConfig]:
    """
    Scan skills directory and load all skills.

    Args:
        skills_directory: Path to skills directory (contains skill subdirs)

    Returns:
        {skill_name: SkillConfig}
    """
    result: Dict[str, SkillConfig] = {}
    if not os.path.isdir(skills_directory):
        return result

    for entry in os.listdir(skills_directory):
        dir_path = os.path.join(skills_directory, entry)
        if not os.path.isdir(dir_path):
            continue
        skill = _parse_skill_yaml(dir_path, entry)
        if skill:
            result[skill.name] = skill

    return result


def build_system_prompt_with_skill(
    base_prompt: str,
    skill: Optional[SkillConfig],
) -> str:
    """
    Merge skill system additions into base prompt.

    Args:
        base_prompt: Base system prompt
        skill: Active skill, None if none

    Returns:
        Merged full system prompt
    """
    if not skill:
        return base_prompt

    additions = skill.get_system_additions()
    if not additions:
        return base_prompt

    return (
        base_prompt
        + "\n\n[Active Skill: "
        + skill.name
        + "]\n"
        + skill.description
        + "\n\n"
        + additions
    )


def match_skill_by_input(user_input: str, skills: Dict[str, SkillConfig]) -> Optional[str]:
    """
    Match skill by user input keywords.

    Args:
        user_input: User input text
        skills: All loaded skills

    Returns:
        Matched skill name, or None
    """
    lower = user_input.lower()
    for name, cfg in skills.items():
        if any(kw.lower() in lower for kw in cfg.trigger_keywords):
            return name
    return None
