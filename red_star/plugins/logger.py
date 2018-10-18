from datetime import datetime, timedelta
from discord import AuditLogAction, Forbidden
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import ChannelNotFoundError, CommandSyntaxError
from red_star.rs_utils import split_message, respond
from red_star.command_dispatcher import Command


class DiscordLogger(BasePlugin):
    name = "logger"
    version = "1.4"
    author = "medeor413, GTG3000"
    description = "A plugin that logs certain events and prints them to a defined log channel " \
                  "in an easily-readable manner."
    default_config = {
        "default": {
            "log_event_blacklist": [
            ]
        }
    }

    async def activate(self):
        self.log_items = {}

    async def on_global_tick(self, *_):
        for guild in self.client.guilds:
            gid = str(guild.id)
            try:
                log_channel = self.channel_manager.get_channel(guild, "logs")
            except ChannelNotFoundError:
                continue
            if gid in self.log_items and self.log_items[gid]:
                logs = "\n".join(self.log_items[gid])
                for msg in split_message(logs, splitter="\n"):
                    await log_channel.send(msg)
                self.log_items[gid].clear()

    async def on_message_delete(self, msg):
        blacklist = self.plugin_config.setdefault(str(msg.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "message_delete" not in blacklist and msg.author != self.client.user:
            contents = msg.clean_content if msg.clean_content else msg.system_content
            msgtime = msg.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            attaches = ""
            if msg.attachments:
                links = ", ".join([x.url for x in msg.attachments])
                attaches = f"\n**Attachments:** `{links}`"
            self.emit_log(f"**ANALYSIS: User {msg.author}'s message at `{msgtime}` in {msg.channel.mention}"
                          f" was deleted. ANALYSIS: Contents:**\n{contents}{attaches}", msg.guild)

    async def on_message_edit(self, before, after):
        blacklist = self.plugin_config.setdefault(str(after.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "message_edit" not in blacklist and after.author != self.client.user:
            old_contents = before.clean_content
            contents = after.clean_content
            if old_contents == contents:
                return
            msgtime = after.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            self.emit_log(f"**ANALYSIS: User {after.author} edited their message at `{msgtime}` in "
                          f"{after.channel.mention}. ANALYSIS:**\n**Old contents:** {old_contents}\n"
                          f"**New contents:** {contents}", after.guild)

    async def on_member_update(self, before, after):
        blacklist = self.plugin_config.setdefault(str(after.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "member_update" not in blacklist:
            diff_str = ""
            if before.name != after.name or before.discriminator != after.discriminator:
                diff_str = f"`Old username: `{before}\n`New username: `{after}\n"
            if before.avatar != after.avatar:
                diff_str = f"{diff_str}`New avatar: `{after.avatar_url}\n"
            if before.nick != after.nick:
                diff_str = f"{diff_str}`Old nick: `{before.nick}\n`New nick: `{after.nick}\n"
            if before.roles != after.roles:
                old_roles = ", ".join([str(x) for x in before.roles])
                new_roles = ", ".join([str(x) for x in after.roles])
                diff_str = f"{diff_str}**Old roles:**```[ {old_roles} ]```\n**New roles:**```[ {new_roles} ]```\n"
            if not diff_str:
                return
            self.emit_log(f"**ANALYSIS: User {after} was modified:**\n{diff_str}", after.guild)

    async def on_guild_channel_pins_update(self, channel, last_pin):
        blacklist = self.plugin_config.setdefault(str(channel.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "guild_channel_pins_update" not in blacklist:
            try:
                new_pin = (datetime.utcnow() - last_pin < timedelta(seconds=5))
            except TypeError:  # last_pin can be None if the last pin in a channel was unpinned
                new_pin = False
            if new_pin:  # Get the pinned message if it's a new pin; can't get the unpinned messages sadly
                msg = (await channel.pins())[0]
                pin_contents = f"\n**Message: {str(msg.author)}:** {msg.clean_content}"
            self.emit_log(f"**ANALYSIS: A message was {'' if new_pin else 'un'}pinned in {channel.mention}.**"
                          f"{pin_contents if new_pin else ''}", channel.guild)

    async def on_member_ban(self, guild, member):
        blacklist = self.plugin_config.setdefault(str(guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "on_member_ban" not in blacklist:
            self.emit_log(f"**ANALYSIS: User {member} was banned.**", guild)

    async def on_member_unban(self, guild, member):
        blacklist = self.plugin_config.setdefault(str(guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "on_member_unban" not in blacklist:
            self.emit_log(f"**ANALYSIS: Ban was lifted from user {member}.**", guild)

    async def on_member_join(self, member):
        blacklist = self.plugin_config.setdefault(str(member.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "on_member_join" not in blacklist:
            self.emit_log(f"**ANALYSIS: User {member} has joined the server. User id: `{member.id}`**", member.guild)

    async def on_member_remove(self, member):
        blacklist = self.plugin_config.setdefault(str(member.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "on_member_remove" not in blacklist:
            now = datetime.utcnow()
            try:
                # find audit log entries for kicking of member with our ID, created in last five seconds.
                # Hopefully five seconds is enough
                latest_logs = member.guild.audit_logs(action=AuditLogAction.kick, after=now - timedelta(seconds=5))
                kick_event = await latest_logs.get(target__id=member.id)
            except Forbidden:
                kick_event = None
            if kick_event:
                kicker = kick_event.user
                reason_str = f"Reason: {kick_event.reason}; " if kick_event.reason else ""
                self.emit_log(f"**ANALYSIS: User {member} was kicked from the server by {kicker}. "
                              f"{reason_str}User id: `{member.id}`**", member.guild)
            else:
                self.emit_log(f"**ANALYSIS: User {member} has left the server. User id: `{member.id}`**", member.guild)

    async def on_guild_role_update(self, before, after):
        blacklist = self.plugin_config.setdefault(str(after.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "on_guild_role_update" not in blacklist:
            diff = []
            try:
                audit_event = after.guild.audit_logs(action=AuditLogAction.role_update,
                                                     after=datetime.utcnow() - timedelta(seconds=5)).get()
            except Forbidden:
                audit_event = None

            if before == after:
                if audit_event:
                    before_dict = audit_event.changes.before.__dict__
                    before.name = before_dict.get("name", after.name)
                    before.colour = before_dict.get("colour", after.colour)
                    before.hoist = before_dict.get("hoist", after.hoist)
                    before.mentionable = before_dict.get("mentionable", after.mentionable)
                    before.permissions = before_dict.get("permissions", after.permissions)
                else:
                    return

            if before.name != after.name:
                diff.append(f"Name changed from {before.name} to {after.name}")
            if before.position != after.position:
                diff.append(f"Position changed from {before.position} to {after.position}")
            if before.colour != after.colour:
                diff.append(f"Colour changed from {before.colour} to {after.colour}")
            if before.hoist != after.hoist:
                diff.append("Is now displayed separately." if after.hoist else "Is no longer displayed separately.")
            if before.mentionable != after.mentionable:
                diff.append("Can now be mentioned." if after.mentionable else "Can no longer be mentioned.")
            if before.permissions != after.permissions:
                # comparing both sets of permissions, PITA
                before_perms = {x: y for x, y in before.permissions}
                after_perms = {x: y for x, y in after.permissions}
                perm_diff = "Added permissions: " + ", ".join(x.upper() for x, y in after.permissions if y and not
                                                              before_perms[x])
                perm_diff = perm_diff + "\nRemoved permissions: " \
                            + ", ".join(x.upper() for x, y in before.permissions if y and not after_perms[x])
                diff.append(perm_diff)
            diff = '\n'.join(diff)
            self.emit_log(f"**ANALYSIS: Role {before.name} was changed by {audit_event.user}:**"
                          f"```\n{diff}```", after.guild)

    async def on_log_event(self, guild, string, *, log_type="log_event"):
        blacklist = self.plugin_config.setdefault(str(guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if log_type not in blacklist:
            self.emit_log(string, guild)

    def emit_log(self, log_str, guild):
        guild_log_queue = self.log_items.setdefault(str(guild.id), [])
        stdout_log_str = log_str.replace("`", "").replace("**", "").replace("ANALYSIS: ", "")
        guild_log_queue.append(log_str)
        self.logger.info(stdout_log_str)

    @Command("LogEvent",
             doc="Adds or removes the events to be logged.",
             syntax="[add|remove type]",
             category="bot_management",
             perms={"manage_guild"})
    async def _logevent(self, msg):
        cfg = self.plugin_config.setdefault(str(msg.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        try:
            action, event_type = msg.clean_content.lower().split(" ", 2)[1:]
        except ValueError:
            if len(msg.clean_content.split(" ")) == 1:
                await respond(msg, f"**ANALYSIS: Disabled log events: **`{', '.join(cfg)}`")
                return
            else:
                raise CommandSyntaxError("Invalid number of arguments.")
        if action == "remove":
            if event_type not in cfg:
                cfg.append(event_type)
                self.config_manager.save_config()
                await respond(msg, f"**ANALYSIS: No longer logging events of type {event_type}.**")
            else:
                await respond(msg, f"**ANALYSIS: Event type {event_type} is already disabled.**")
        elif action == "add":
            if event_type in cfg:
                cfg.remove(event_type)
                self.config_manager.save_config()
                await respond(msg, f"**ANALYSIS: Now logging events of type {event_type}.**")
            else:
                await respond(msg, f"**ANALYSIS: Event type {event_type} is already logged.**")
        else:
            raise CommandSyntaxError(f"Action {action} is not a valid action.")
