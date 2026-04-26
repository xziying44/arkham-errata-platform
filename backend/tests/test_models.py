import pytest
from sqlalchemy import select
from app.models import User, UserRole, CardIndex, Errata, ErrataStatus


@pytest.mark.asyncio
async def test_create_user(db):
    user = User(username="test_user", password_hash="hash", role=UserRole.ERRATA)
    db.add(user)
    await db.commit()
    result = await db.execute(select(User).where(User.username == "test_user"))
    u = result.scalar_one()
    assert u.role == UserRole.ERRATA
    assert u.is_active is True


@pytest.mark.asyncio
async def test_create_card_index(db):
    card = CardIndex(arkhamdb_id="01150_ci", name_zh="阿卡姆密林", category="剧本卡")
    db.add(card)
    await db.commit()
    result = await db.execute(select(CardIndex).where(CardIndex.arkhamdb_id == "01150_ci"))
    c = result.scalar_one()
    assert c.name_zh == "阿卡姆密林"


@pytest.mark.asyncio
async def test_create_errata(db):
    card = CardIndex(arkhamdb_id="01150_err", name_zh="测试卡", category="剧本卡")
    user = User(username="editor", password_hash="hash", role=UserRole.ERRATA)
    db.add_all([card, user])
    await db.flush()
    errata = Errata(
        arkhamdb_id="01150_err", user_id=user.id,
        original_content='{"name":"old"}', modified_content='{"name":"new"}',
        status=ErrataStatus.PENDING
    )
    db.add(errata)
    await db.commit()
    result = await db.execute(select(Errata).where(Errata.arkhamdb_id == "01150_err"))
    e = result.scalar_one()
    assert e.status == ErrataStatus.PENDING
