import asyncio
import os
import uuid
import pytest

pytestmark=pytest.mark.skipif(not os.getenv('SDE_TEST_DATABASE_URL'),reason='Explicit isolated test database required')


def test_migration_is_idempotent_and_unprivileged_ledger_is_private():
    async def scenario():
        from sqlalchemy import text
        from jobs import engine
        from scripts.migrate import migrate
        assert engine.url.database.endswith('_test')
        assert engine.url.render_as_string(hide_password=False)==os.environ['SDE_TEST_DATABASE_URL']
        await migrate()
        await migrate()
        role='privacy_fixture_'+uuid.uuid4().hex
        async with engine.connect() as db:
            transaction=await db.begin()
            try:
                assert await db.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='deepfake_jobs'::regclass")) is True
                await db.execute(text(f'CREATE ROLE {role} NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO {role}'))
                await db.execute(text(f'GRANT SELECT ON deepfake_jobs TO {role}'))
                await db.execute(text("INSERT INTO deepfake_jobs (id,token_hash,content_hash,object_key,filename,version,status,attempts,cleanup_pending,created_at) VALUES ('privacy-fixture','token','hash','key','fixture','fixture','completed',0,false,now())"))
                assert await db.scalar(text("SELECT count(*) FROM deepfake_jobs WHERE id='privacy-fixture'"))==1
                await db.execute(text(f'SET LOCAL ROLE {role}'))
                assert await db.scalar(text('SELECT count(*) FROM deepfake_jobs'))==0
            finally:
                await transaction.rollback()
        await engine.dispose()
    asyncio.run(scenario())
