import logging

from ...scaffold import Scaffold


class JoinVoiceCall(Scaffold):
    async def _join_voice_call(
        self,
        params: dict,
    ):
        request_call = {
            'ufrag': params['ufrag'],
            'pwd': params['pwd'],
            'fingerprints': [{
                'hash': params['hash'],
                'setup': params['setup'],
                'fingerprint': params['fingerprint'],
            }],
            'ssrc': params['source'],
        }
        chat_id = int(params['chat_id'])
        try:
            return await self._app.join_group_call(
                chat_id,
                request_call,
                params['invite_hash'],
                self._cache_user_peer.get(chat_id),
            )
        except Exception as e:
            if 'GROUPCALL_FORBIDDEN' in str(e):
                self._cache_user_peer.pop(chat_id)
            logging.error(f'JOIN_VOICE_CALL_ERROR -> {e}')
        return {'transport': None}
