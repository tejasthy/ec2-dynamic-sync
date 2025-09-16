#!/usr/bin/env python3
"""Setup CLI for EC2 Dynamic Sync."""

import click

@click.command()
def setup():
    """Interactive setup wizard for EC2 Dynamic Sync."""
    click.echo("EC2 Dynamic Sync Setup - Coming Soon!")
    click.echo("This will be an interactive setup wizard.")

if __name__ == '__main__':
    setup()
