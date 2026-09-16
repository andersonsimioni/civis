"""
Attendant certification package (Onda-1 F2).

Given a directory of CIVIS sessions with `verdict.json`, decide whether
an attendant is eligible for a certification level (BRONZE/SILVER/GOLD)
and, if so, render a printable PDF certificate.

Two orthogonal modules:

    - eligibility.py — pure aggregation logic over verdict.json files.
    - pdf_generator.py — one-page A4 certificate renderer (reportlab).

Public surface is small on purpose: the CLI (`civis certify`) is the
only intended caller today.
"""
