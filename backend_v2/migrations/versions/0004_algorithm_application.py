"""Add opt-in ALGORITHM and explicit evidence sources; preserve legacy rows."""
from alembic import op
import sqlalchemy as sa

revision='0004_algorithm_application'
down_revision='0003_user_credentials'
branch_labels=None
depends_on=None


def _replace(table_name, marker, expression, name):
    bind=op.get_bind()
    if bind.dialect.name=='sqlite':
        # Reflection retains keys, foreign keys and indexes. Replace only the
        # selected check; old unnamed SQLite checks cannot be drop_constraint'd.
        table=sa.Table(table_name,sa.MetaData(),autoload_with=bind)
        for c in list(table.constraints):
            if isinstance(c,sa.CheckConstraint) and marker in str(c.sqltext):table.constraints.remove(c)
        table.append_constraint(sa.CheckConstraint(expression,name=name))
        with op.batch_alter_table(table_name,recreate='always',copy_from=table):pass
    else:
        for c in sa.inspect(bind).get_check_constraints(table_name):
            if marker in c['sqltext']:op.drop_constraint(c['name'],table_name,type_='check')
        op.create_check_constraint(name,table_name,expression)


def upgrade():
    _replace('inference_jobs','kind',"kind IN ('PREDICTION','OCCLUSION','ALGORITHM')",'ck_jobs_kind_next')
    _replace('inference_results','source',"source IN ('LIVE_CASE','SYNTHETIC','PRECOMPUTED')",'ck_results_source_next')


def downgrade():
    bind=op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM inference_jobs WHERE kind='ALGORITHM'")).scalar() or bind.execute(sa.text("SELECT count(*) FROM inference_results WHERE source<>'LIVE_CASE'")).scalar():
        raise RuntimeError('Preserve new algorithm results before downgrading; no destructive automatic rollback')
    _replace('inference_jobs','kind',"kind IN ('PREDICTION','OCCLUSION')",'ck_jobs_kind_next')
    _replace('inference_results','source',"source = 'LIVE_CASE'",'ck_results_source_next')
