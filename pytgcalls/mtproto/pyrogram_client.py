import json
from typing import Optional, Callable, Dict

from pyrogram import Client, ContinuePropagation
from pyrogram.raw.base import InputPeer
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import GetFullChat
from pyrogram.raw.functions.phone import JoinGroupCall, LeaveGroupCall, EditGroupCallParticipant
from pyrogram.raw.types import InputGroupCall, Updates, DataJSON, UpdateGroupCall, \
    UpdateNewChannelMessage, MessageService, Channel, MessageActionInviteToGroupCall, UpdateChannel, ChannelForbidden, \
    GroupCall, GroupCallDiscarded, UpdateNewMessage, MessageActionChatDeleteUser, PeerChat, ChatForbidden, Chat, \
    InputChannel, InputPeerChannel

from .bridged_client import BridgedClient
from .client_cache import ClientCache


class PyrogramClient(BridgedClient):
    def __init__(
        self,
        cache_duration: int,
        client: Client,
    ):
        self._app: Client = client
        self._handler: Dict[str, Callable] = {}
        self._cache: ClientCache = ClientCache(
            cache_duration,
            self,
        )

        @self._app.on_raw_update()
        async def on_update(_, update, __, data2):
            if isinstance(
                update,
                UpdateGroupCall,
            ):
                chat_id = self.chat_id(data2[update.chat_id])
                if isinstance(
                    update.call,
                    GroupCall,
                ):
                    self._cache.set_cache(
                        chat_id,
                        InputGroupCall(
                            access_hash=update.call.access_hash,
                            id=update.call.id,
                        ),
                    )
                if isinstance(
                    update.call,
                    GroupCallDiscarded,
                ):
                    self._cache.drop_cache(chat_id)
                    if 'CLOSED_HANDLER' in self._handler:
                        await self._handler['CLOSED_HANDLER'](
                            chat_id,
                        )
            if isinstance(
                update,
                UpdateChannel,
            ):
                chat_id = self.chat_id(update)
                if len(data2) > 0:
                    if isinstance(
                        data2[update.channel_id],
                        ChannelForbidden,
                    ):
                        self._cache.drop_cache(chat_id)
                        if 'KICK_HANDLER' in self._handler:
                            await self._handler['KICK_HANDLER'](
                                chat_id,
                            )
            if isinstance(
                update,
                UpdateNewChannelMessage,
            ) or isinstance(
                update,
                UpdateNewMessage,
            ):
                if isinstance(
                    update.message,
                    MessageService,
                ):
                    if isinstance(
                        update.message.action,
                        MessageActionInviteToGroupCall,
                    ):
                        if 'INVITE_HANDLER' in self._handler:
                            await self._handler['INVITE_HANDLER'](update.message.action)
                    if isinstance(
                        update.message.action,
                        MessageActionChatDeleteUser,
                    ):
                        if isinstance(
                            update.message.peer_id,
                            PeerChat,
                        ):
                            chat_id = self.chat_id(update.message.peer_id)
                            if isinstance(
                                data2[update.message.peer_id.chat_id],
                                ChatForbidden,
                            ):
                                self._cache.drop_cache(chat_id)
                                if 'KICK_HANDLER' in self._handler:
                                    await self._handler['KICK_HANDLER'](
                                        chat_id,
                                    )

            if isinstance(
                data2,
                Dict,
            ):
                for group_id in data2:
                    if isinstance(
                        update,
                        UpdateNewChannelMessage,
                    ) or isinstance(
                        update,
                        UpdateNewMessage,
                    ):
                        if isinstance(
                            update.message,
                            MessageService,
                        ):
                            if isinstance(
                                data2[group_id],
                                Channel,
                            ) or isinstance(
                                data2[group_id],
                                Chat,
                            ):
                                chat_id = self.chat_id(data2[group_id])
                                if data2[group_id].left:
                                    self._cache.drop_cache(
                                        chat_id,
                                    )
                                    if 'LEFT_HANDLER' in self._handler:
                                        await self._handler['LEFT_HANDLER'](
                                            chat_id,
                                        )
            raise ContinuePropagation()

    def on_closed_voice_chat(self) -> Callable:
        def decorator(func: Callable) -> Callable:
            if self is not None:
                self._handler['CLOSED_HANDLER'] = func
            return func
        return decorator

    def on_kicked(self) -> Callable:
        def decorator(func: Callable) -> Callable:
            if self is not None:
                self._handler['KICK_HANDLER'] = func
            return func
        return decorator

    def on_receive_invite(self) -> Callable:
        def decorator(func: Callable) -> Callable:
            if self is not None:
                self._handler['INVITE_HANDLER'] = func
            return func
        return decorator

    def on_left_group(self) -> Callable:
        def decorator(func: Callable) -> Callable:
            if self is not None:
                self._handler['LEFT_HANDLER'] = func
            return func
        return decorator

    async def get_call(
        self,
        chat_id: int,
    ) -> Optional[InputGroupCall]:
        chat = await self._app.resolve_peer(chat_id)
        if isinstance(chat, InputPeerChannel):
            return (
                await self._app.send(
                    GetFullChannel(channel=InputChannel(
                        channel_id=chat.channel_id,
                        access_hash=chat.access_hash,
                    )),
                )
            ).full_chat.call
        else:
            return (
                await self._app.send(
                    GetFullChat(chat_id=chat.chat_id),
                )
            ).full_chat.call

    async def join_group_call(
        self,
        chat_id: int,
        json_join: dict,
        invite_hash: str,
        join_as: InputPeer,
    ):
        chat_call = await self._cache.get_full_chat(chat_id)
        if chat_call is not None:
            result: Updates = await self._app.send(
                JoinGroupCall(
                    call=chat_call,
                    params=DataJSON(data=json.dumps(json_join)),
                    muted=False,
                    join_as=join_as,
                    invite_hash=invite_hash,
                ),
            )
            for update in result.updates:
                if isinstance(update, UpdateGroupCall):
                    transport = json.loads(update.call.params.data)[
                        'transport'
                    ]
                    return {
                        'transport': {
                            'ufrag': transport['ufrag'],
                            'pwd': transport['pwd'],
                            'fingerprints': transport['fingerprints'],
                            'candidates': transport['candidates'],
                        },
                    }
        return {'transport': None}

    async def leave_group_call(
        self,
        chat_id: int,
    ):
        chat_call = await self._cache.get_full_chat(chat_id)
        if chat_call is not None:
            await self._app.send(
                LeaveGroupCall(
                    call=chat_call,
                    source=0,
                ),
            )

    async def change_volume(
        self,
        chat_id: int,
        volume: int,
        participant: InputPeer,
    ):
        chat_call = await self._cache.get_full_chat(chat_id)
        if chat_call is not None:
            await self._app.send(
                EditGroupCallParticipant(
                    call=chat_call,
                    participant=participant,
                    muted=False,
                    volume=volume * 100,
                ),
            )

    async def get_full_chat(self, chat_id: int):
        return await self._cache.get_full_chat(chat_id)

    async def resolve_peer(
        self,
        user_id: int,
    ) -> InputPeer:
        return await self._app.resolve_peer(user_id)

    async def get_id(self) -> int:
        return (await self._app.get_me())['id']

    def is_connected(self) -> bool:
        return self._app.is_connected

    async def start(self):
        await self._app.start()
