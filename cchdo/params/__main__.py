import json
from importlib.resources import as_file, files
from textwrap import dedent

import click


@click.group()
def cli():
    pass


@cli.group()
def cf():
    """Maniuplate the CF Standard Names"""


@cli.group()
def whp():
    """Maniuplate the WHP name list"""


@cf.command(name="update")
@click.argument("cf_xml", type=click.Path(exists=True))
def cf_update(cf_xml):
    from xml.etree import ElementTree

    from .db import CFAlias, CFName, ConfigDict, database

    conf = ConfigDict()
    current_cf_version_number = conf["cf_version_number"]

    cf_names = {}
    cf_aliases = {}
    version_number = None
    last_mod = None
    for element in ElementTree.parse(cf_xml).getroot():
        if element.tag == "version_number":
            version_number = int(element.text)
            if int(current_cf_version_number) >= version_number:
                click.echo(
                    f"Internal CF Version ({current_cf_version_number}) is the same or newer than the cf xml ({version_number})"
                )
                quit(1)
        if element.tag == "last_modified":
            last_mod = element.text

        if element.tag not in ("entry", "alias"):
            continue

        name = element.attrib["id"]
        name_info = {info.tag: info.text for info in element}

        if element.tag == "entry":
            cf_names[name] = {"standard_name": name, **name_info}

        if element.tag == "alias":
            cf_aliases[name] = {"alias": name, "standard_name": name_info["entry_id"]}

    with database() as session:
        exising_cf_names = {r.standard_name: r for r in session.query(CFName).all()}
        existing_cf_aliases = {r.alias: r for r in session.query(CFAlias).all()}

        for alias, record in cf_aliases.items():
            if alias not in existing_cf_aliases:
                session.add(CFAlias(**cf_aliases[alias]))
            elif record["standard_name"] != existing_cf_aliases[alias].standard_name:
                existing = existing_cf_aliases[alias]
                existing.standard_name = cf_aliases[alias]["standard_name"]
                session.add(existing)
        for alias, record in existing_cf_aliases.items():
            if alias not in cf_aliases:
                session.delete(existing_cf_aliases[alias])

        for name, record in cf_names.items():
            if name not in exising_cf_names:
                session.add(CFName(**record))
            else:
                dirty = False
                existing = exising_cf_names[name]
                for key, value in record.items():
                    if getattr(existing, key) != value:
                        dirty = True
                        setattr(existing, key, value)
                if dirty:
                    session.add(existing)
        for name, record in exising_cf_names.items():
            if name not in cf_names:
                session.delete(exising_cf_names[name])

        if len(session.new) > 0:
            print("Objects to be added:")
            for obj in session.new:
                print(obj)
        if len(session.deleted) > 0:
            print("Objects to be removed:")
            for obj in session.deleted:
                print(obj)
        if len(session.dirty) > 0:
            print("Objects to be modified:")
            for obj in session.dirty:
                print(obj)
        session.commit()

    conf["cf_version_number"] = version_number
    conf["cf_last_modified"] = last_mod


@whp.command(name="json")
def ex_json():
    from . import WHPNames

    print(json.dumps(WHPNames.legacy_json, indent=2, sort_keys=True))


@cli.command()
def dump_db():
    import sqlite3

    with as_file(files("cchdo.params") / "params.sqlite3") as p:
        with sqlite3.connect(p) as conn:
            with p.with_suffix(".sqlite3.sql").open("w") as f:
                for line in conn.iterdump():
                    f.write(f"{line}\n")


@cli.command()
def gen_code():
    from jinja2 import Template
    from sqlalchemy import select

    from .db import Alias, CFAlias, CFName, WHPName, database

    template = Template(
        dedent(
            """\
    # pylint: skip-file
    # auto generated, do not modify
    from cchdo.params.core import WHPName as WHPNameDC

    whp_names = dict()
    names = [
    {% for name in  whpnames -%}
    {{name.code}},
    {% endfor -%}
    ]
    for name in names:
        whp_names[name.key] = name

    _aliases = {
    {% for alias in aliases -%}
    {{"(%r, %r)"| format(alias.old_name, alias.old_unit)}}: {{"(%r, %r)"| format(alias.whp_name, alias.whp_unit)}},
    {% endfor -%}
    }

    """
        )
    )

    with database() as session:
        whpnames = session.execute(select(WHPName)).scalars().all()
        aliases = session.execute(select(Alias)).scalars().all()
        whp_names_code = template.render(whpnames=whpnames, aliases=aliases)

    with as_file(files("cchdo.params") / "_whp_names.py") as p:
        with p.open("w") as f:
            f.write(whp_names_code)

    # CF names
    template = Template(
        dedent(
            """\
    # pylint: skip-file
    # auto generated, do not modify
    from cchdo.params.core import CFStandardName as CFStandardNameDC

    cf_standard_names = dict()
    names = [
    {% for name in  cfnames -%}
    {{name.code}},
    {% endfor -%}
    ]
    for name in names:
        cf_standard_names[name.name] = name
    {% for alias in aliases -%}
    cf_standard_names["{{alias.alias}}"] = cf_standard_names["{{alias.standard_name}}"]
    {% endfor -%}
    """
        )
    )
    with database() as session:
        cfnames = session.execute(select(CFName)).scalars().all()
        aliases = session.execute(select(CFAlias)).scalars().all()
        cf_names_code = template.render(cfnames=cfnames, aliases=aliases)

    with as_file(files("cchdo.params") / "_cf_names.py") as p:
        with p.open("w") as f:
            f.write(cf_names_code)


if __name__ == "__main__":
    cli()
