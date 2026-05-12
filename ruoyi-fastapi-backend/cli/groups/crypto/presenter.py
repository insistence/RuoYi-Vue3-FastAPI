class CryptoCommandPresenter:
    """
    传输加密命令文本渲染器。

    该渲染器负责将 `crypto` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_crypto_keygen_text(self, payload: dict[str, object]) -> str:
        """
        将密钥生成结果渲染为文本摘要。

        :param payload: 密钥生成结果字典
        :return: 文本摘要
        """
        env_patch = payload.get('envPatch')
        env_patch_keys = sorted(env_patch.keys()) if isinstance(env_patch, dict) else []
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'kid: {payload.get("kid", "-")}',
            f'key_size: {payload.get("keySize", "-")}',
        ]
        lines.extend(self._build_multiline_block('public_key', payload.get('publicKey')))
        lines.extend(self._build_multiline_block('private_key', payload.get('privateKey')))
        if env_patch_keys:
            lines.append('env_patch_keys:')
            lines.extend(f'  - {key}' for key in env_patch_keys)
        else:
            lines.append('env_patch_keys: none')
        return '\n'.join(lines)

    def build_export_public_text(self, payload: dict[str, object]) -> str:
        """
        将公钥导出结果渲染为文本摘要。

        :param payload: 公钥导出结果字典
        :return: 文本摘要
        """
        public_key_payload = payload.get('publicKey')
        if not isinstance(public_key_payload, dict):
            return '\n'.join(
                [
                    f'ok: {str(payload.get("ok", False)).lower()}',
                    f'env: {payload.get("env", "")}',
                    'public_key: none',
                ]
            )

        supported_kids = public_key_payload.get('supportedKids')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'kid: {public_key_payload.get("kid", "-")}',
            f'alg: {public_key_payload.get("alg", "-")}',
            f'envelope_version: {public_key_payload.get("envelopeVersion", "-")}',
            f'expire_at: {public_key_payload.get("expireAt", "-")}',
        ]
        if isinstance(supported_kids, list) and supported_kids:
            lines.append('supported_kids:')
            lines.extend(f'  - {kid}' for kid in supported_kids)
        else:
            lines.append('supported_kids: none')
        lines.extend(self._build_multiline_block('public_key_pem', public_key_payload.get('publicKey')))
        return '\n'.join(lines)

    @staticmethod
    def _build_multiline_block(title: str, value: object) -> list[str]:
        """
        将多行文本构建为带标题的块级文本。

        :param title: 块标题
        :param value: 原始文本值
        :return: 文本行列表
        """
        text = '' if value is None else str(value).strip()
        if not text:
            return [f'{title}: -']
        return [f'{title}:', '  |', *[f'    {line}' for line in text.splitlines()]]
