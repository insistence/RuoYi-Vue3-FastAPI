class DbCommandPresenter:
    """
    数据库命令文本渲染器。

    该渲染器负责将 `db` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    @staticmethod
    def build_current_revision_text(payload: dict[str, object]) -> str:
        """
        将数据库当前迁移版本结果渲染为文本摘要。

        :param payload: 当前迁移版本结果字典
        :return: 文本摘要
        """
        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'env: {payload.get("env", "")}',
                f'current_revision: {payload.get("currentRevision", "-")}',
            ]
        )

    def build_alembic_revisions_text(self, payload: dict[str, object]) -> str:
        """
        将 Alembic 修订版本结果渲染为文本摘要。

        :param payload: 修订版本结果字典
        :return: 文本摘要
        """
        items = payload.get('items')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'message: {payload.get("message", "-")}',
            f'count: {payload.get("count", 0)}',
        ]
        if 'totalCount' in payload:
            lines.append(f'total_count: {payload.get("totalCount", 0)}')
        if 'limit' in payload:
            lines.append(f'limit: {payload.get("limit", 0)}')
        if not isinstance(items, list) or not items:
            lines.append('items: none')
            return '\n'.join(lines)

        lines.append('items:')
        for item in items:
            if isinstance(item, dict):
                lines.extend([f'  {line}' for line in self._build_alembic_revision_item_lines(item)])
        return '\n'.join(lines)

    @staticmethod
    def _build_alembic_revision_item_lines(revision_item: dict[str, object]) -> list[str]:
        """
        构建单个 Alembic 修订版本的文本行。

        :param revision_item: 修订版本结果字典
        :return: 文本行列表
        """
        down_revisions = revision_item.get('downRevisions')
        branch_labels = revision_item.get('branchLabels')
        depends_on = revision_item.get('dependsOn')
        return [
            f'- revision: {revision_item.get("revision", "-")}',
            f'  down_revisions: {",".join(down_revisions) if isinstance(down_revisions, list) and down_revisions else "-"}',
            f'  branch_labels: {",".join(branch_labels) if isinstance(branch_labels, list) and branch_labels else "-"}',
            f'  depends_on: {",".join(depends_on) if isinstance(depends_on, list) and depends_on else "-"}',
            f'  doc: {revision_item.get("doc", "") or "-"}',
            f'  path: {revision_item.get("path", "-")}',
        ]
