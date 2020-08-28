import click


@click.group()
def cli():
    pass


@cli.command()
def dump_db():
    from importlib.resources import path
    import sqlite3

    with path("cchdo.params", "params.sqlite3") as p:
        with sqlite3.connect(p) as conn:
            with open(f"{p}.sql", "w") as f:
                for line in conn.iterdump():
                    f.write(f"{line}\n")

@cli.command()
def params_to_json():
    import json
    from . import WHPNames
    
    print(json.dumps(WHPNames.legacy_json, indent=2))

cli()
