# ============================================================
# GREEN App — Column types shared by the models and the migrations
# Production runs on MySQL/MariaDB (o2switch); SQLite in development;
# PostgreSQL (former Supabase database) stays readable for the data copy.
# Each type renders the same as before on SQLite and PostgreSQL, and picks
# the MySQL type that keeps the same behaviour there.
# ============================================================

from sqlalchemy import JSON, DateTime, Float, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.postgresql import JSONB

# jsonb on PostgreSQL (indexable, compact), JSON elsewhere (LONGTEXT
# checked by json_valid on MariaDB)
JSONType = JSON().with_variant(JSONB(), "postgresql")

# MySQL FLOAT is single precision (~7 digits: GPS positions would lose
# decimetres); DOUBLE matches PostgreSQL's double precision. asdecimal=False
# returns float, not Decimal, like the other databases.
FloatType = Float().with_variant(mysql.DOUBLE(asdecimal=False), "mysql")

# MySQL DATETIME drops the microseconds by default: two chat messages saved
# in the same second would no longer sort reliably.
DateTimeType = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")

# MySQL TEXT stops at 64 KB; MEDIUMTEXT (16 MB) is closer to PostgreSQL's
# unbounded text (long GreenBot answers, notes).
TextType = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")

# Table options for MySQL: InnoDB (foreign keys, transactions) and utf8mb4
# (accents and emoji), whatever the server defaults are.
MYSQL_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}
