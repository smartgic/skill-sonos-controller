from setuptools import setup
from os import getenv, path, walk

SKILL_NAME = "skill-sonos-controller"
SKILL_PKG = SKILL_NAME.replace("-", "_")
PLUGIN_ENTRY_POINT = f"{SKILL_NAME}.smartgic={SKILL_PKG}:SonosController"
BASE_PATH = path.abspath(path.dirname(__file__))


def get_requirements(requirements_filename: str):
    requirements_file = path.join(BASE_PATH, requirements_filename)
    with open(requirements_file, "r", encoding="utf-8") as r:
        requirements = r.readlines()
    requirements = [
        r.strip() for r in requirements if r.strip() and not r.strip().startswith("#")
    ]

    for i in range(0, len(requirements)):
        r = requirements[i]
        if "@" in r:
            parts = [
                p.lower() if p.strip().startswith("git+http") else p
                for p in r.split("@")
            ]
            r = "@".join(parts)
        if getenv("GITHUB_TOKEN"):
            if "github.com" in r:
                requirements[i] = r.replace(
                    "github.com", f"{getenv('GITHUB_TOKEN')}@github.com"
                )
    return requirements


def find_resource_files():
    resource_base_dirs = ("locale", "ui", "vocab", "dialog", "regex")
    base_dir = BASE_PATH
    package_data = ["skill.json"]
    for res in resource_base_dirs:
        if path.isdir(path.join(base_dir, res)):
            for directory, _, files in walk(path.join(base_dir, res)):
                if files:
                    package_data.append(
                        path.join(directory.replace(base_dir, "").lstrip("/"), "*")
                    )
    return package_data


with open(path.join(BASE_PATH, "README.md"), "r") as f:
    long_description = f.read()

with open(path.join(BASE_PATH, "version.py"), "r", encoding="utf-8") as v:
    for line in v.readlines():
        if line.startswith("__version__"):
            if '"' in line:
                version = line.split('"')[1]
            else:
                version = line.split("'")[1]

setup(
    name=f"smartgic-{SKILL_NAME}",
    version=version,
    url="https://github.com/smartgic/mycroft-sonos-controller-skill",
    license="MIT",
    install_requires=get_requirements("requirements.txt"),
    author="Smart'Gic",
    author_email="gaetan.trellu@smartgic.io",
    long_description=long_description,
    long_description_content_type="text/markdown",
    package_dir={SKILL_PKG: ""},
    packages=[SKILL_PKG],
    package_data={SKILL_PKG: find_resource_files()},
    include_package_data=True,
    entry_points={"ovos.plugin.skill": PLUGIN_ENTRY_POINT},
)
