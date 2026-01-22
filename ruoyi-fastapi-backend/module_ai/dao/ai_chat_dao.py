from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_ai.entity.do.ai_chat_do import AiChatConfig
from module_ai.entity.vo.ai_chat_vo import AiChatConfigModel


class AiChatConfigDao:
    """
    AI对话配置数据库操作层
    """

    @classmethod
    async def get_chat_config_detail_by_user_id(cls, db: AsyncSession, user_id: int) -> AiChatConfig | None:
        """
        根据用户ID获取配置

        :param db: orm对象
        :param user_id: 用户ID
        :return: 配置对象
        """
        ai_chat_config = (
            (await db.execute(select(AiChatConfig).where(AiChatConfig.user_id == user_id))).scalars().first()
        )

        return ai_chat_config

    @classmethod
    async def add_chat_config_dao(cls, db: AsyncSession, chat_config: AiChatConfigModel) -> AiChatConfig:
        """
        新增对话配置数据库操作

        :param db: orm对象
        :param chat_config: 对话配置对象
        :return: 配置对象
        """
        db_chat_config = AiChatConfig(**chat_config.model_dump(exclude_unset=True))
        db.add(db_chat_config)
        await db.flush()

        return db_chat_config

    @classmethod
    async def edit_chat_config_dao(cls, db: AsyncSession, chat_config: dict) -> None:
        """
        编辑对话配置数据库操作

        :param db: orm对象
        :param chat_config: 需要更新的对话配置字典
        :return:
        """
        await db.execute(update(AiChatConfig), [chat_config])
