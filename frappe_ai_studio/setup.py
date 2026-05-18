# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="frappe_ai_studio",
    version="0.0.1",
    description="A Self-Modifying Developer Agent for the Frappe Framework",
    author="Frappe AI Studio",
    author_email="ai@example.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
