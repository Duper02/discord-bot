"""
╔══════════════════════════════════════════════════════════╗
║         FULL-FEATURED DISCORD BOT  —  Koya-style         ║
║  Categories: Moderation · Levels · Fun · Social · Utility ║
║              Animals · Image · Info · Admin · AFK         ║
╚══════════════════════════════════════════════════════════╝
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import json, os, random, asyncio, math, aiohttp
from datetime import timedelta, datetime
from collections import defaultdict

# ══════════════════════════════════════════
#  BOT SETUP
# ══════════════════════════════════════════
import os
TOKEN  = os.environ.get("TOKEN", "YOUR_TOKEN_HERE")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
PREFIX = "!"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)
tree = bot.tree

# ══════════════════════════════════════════
#  DATA HELPERS
# ══════════════════════════════════════════
def load(path, default=None):
    if default is None: default = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── in-memory stores (persisted to JSON) ──
custom_commands = load("custom_commands.json")
welcome_cfg     = load("welcome_config.json", {
    "channel_id": None, "message": "Welcome {mention} to {server}! You are member #{count}.",
    "embed_color": 0x5865F2, "embed_title": "👋 New Member!", "show_member_count": True,
})
xp_data         = load("xp_data.json")          # {guild_id: {user_id: {xp, level}}}
economy_data    = load("economy_data.json")      # {user_id: {balance, daily_streak, last_daily}}
warns_data      = load("warns_data.json")        # {guild_id: {user_id: [{reason, date, mod}]}}
modlogs_data    = load("modlogs_data.json")      # {guild_id: [{type,user,mod,reason,date}]}
afk_data        = load("afk_data.json")          # {user_id: {message, since}}
autoroles       = load("autoroles.json")         # {guild_id: [{role_id, type}]}
marriages       = load("marriages.json")         # {user_id: [partner_ids]}
families        = load("families.json")          # {user_id: {parent, children}}
lovecalcs       = load("lovecalcs.json")         # {pair_key: value}
slowmode_data   = load("slowmode_data.json")     # {channel_id: seconds}
checklist_data  = load("checklist_data.json")    # {user_id: [items]}
automod_cfg     = load("automod_config.json")    # {guild_id: {anti_scam, anti_poll}}
level_roles     = load("level_roles.json")       # {guild_id: {level: role_id}}
persist_roles   = load("persist_roles.json")     # {guild_id: {user_id: [role_ids]}}

# ══════════════════════════════════════════
#  WELCOME PANEL  (interactive UI)
# ══════════════════════════════════════════
def build_welcome_embed(guild):
    ch_id = welcome_cfg.get("channel_id")
    ch    = guild.get_channel(int(ch_id)) if ch_id else None
    color = welcome_cfg.get("embed_color", 0x5865F2)
    embed = discord.Embed(title="⚙️ Welcome Panel", description="Configure the welcome system.", color=color)
    embed.add_field(name="📢 Channel",      value=ch.mention if ch else "`Not set`", inline=True)
    embed.add_field(name="🎨 Color",        value=f"`#{hex(color)[2:].upper()}`",    inline=True)
    embed.add_field(name="🔢 Member count", value="✅" if welcome_cfg.get("show_member_count") else "❌", inline=True)
    embed.add_field(name="📝 Title",   value=welcome_cfg.get("embed_title", "N/A"), inline=False)
    embed.add_field(name="💬 Message", value=welcome_cfg.get("message", "N/A"),    inline=False)
    embed.set_footer(text="Placeholders: {mention} {name} {server} {count}")
    return embed

class WelcomeMsgModal(ui.Modal, title="Edit Welcome Message"):
    t = ui.TextInput(label="Embed Title",   max_length=100)
    m = ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=500)
    def __init__(self, view):
        super().__init__()
        self.v = view
        self.t.default = welcome_cfg.get("embed_title","")
        self.m.default = welcome_cfg.get("message","")
    async def on_submit(self, i):
        welcome_cfg["embed_title"] = self.t.value
        welcome_cfg["message"]     = self.m.value
        save("welcome_config.json", welcome_cfg)
        await i.response.edit_message(embed=build_welcome_embed(i.guild), view=self.v)

class WelcomeColorModal(ui.Modal, title="Set Embed Color"):
    c = ui.TextInput(label="Hex Color (without #)", min_length=6, max_length=6)
    def __init__(self, view):
        super().__init__()
        self.v = view
    async def on_submit(self, i):
        try:
            welcome_cfg["embed_color"] = int(self.c.value, 16)
            save("welcome_config.json", welcome_cfg)
            await i.response.edit_message(embed=build_welcome_embed(i.guild), view=self.v)
        except ValueError:
            await i.response.send_message("❌ Invalid hex.", ephemeral=True)

class WelcomeChannelModal(ui.Modal, title="Set Welcome Channel"):
    cid = ui.TextInput(label="Channel ID", placeholder="Right-click channel → Copy ID")
    def __init__(self, view):
        super().__init__()
        self.v = view
    async def on_submit(self, i):
        try:
            ch = i.guild.get_channel(int(self.cid.value.strip()))
            if not ch:
                await i.response.send_message("❌ Channel not found.", ephemeral=True); return
            welcome_cfg["channel_id"] = ch.id
            save("welcome_config.json", welcome_cfg)
            await i.response.edit_message(embed=build_welcome_embed(i.guild), view=self.v)
        except ValueError:
            await i.response.send_message("❌ Invalid ID.", ephemeral=True)

class WelcomePanel(ui.View):
    def __init__(self): super().__init__(timeout=300)
    @ui.button(label="📢 Channel",       style=discord.ButtonStyle.primary,   row=0)
    async def ch(self, i, b):  await i.response.send_modal(WelcomeChannelModal(self))
    @ui.button(label="💬 Message",       style=discord.ButtonStyle.primary,   row=0)
    async def msg(self, i, b): await i.response.send_modal(WelcomeMsgModal(self))
    @ui.button(label="🎨 Color",         style=discord.ButtonStyle.primary,   row=0)
    async def col(self, i, b): await i.response.send_modal(WelcomeColorModal(self))
    @ui.button(label="🔢 Toggle Count",  style=discord.ButtonStyle.secondary, row=1)
    async def cnt(self, i, b):
        welcome_cfg["show_member_count"] = not welcome_cfg.get("show_member_count", True)
        save("welcome_config.json", welcome_cfg)
        await i.response.edit_message(embed=build_welcome_embed(i.guild), view=self)
    @ui.button(label="👀 Test",          style=discord.ButtonStyle.success,   row=1)
    async def tst(self, i, b):
        await i.response.defer(ephemeral=True)
        await send_welcome(i.user)
        await i.followup.send("✅ Test sent!", ephemeral=True)
    @ui.button(label="❌ Close",         style=discord.ButtonStyle.danger,    row=1)
    async def cls(self, i, b): await i.message.delete()

# ══════════════════════════════════════════
#  LEVEL SYSTEM
# ══════════════════════════════════════════
def get_xp(guild_id, user_id):
    g, u = str(guild_id), str(user_id)
    return xp_data.get(g, {}).get(u, {"xp": 0, "level": 0})

def add_xp(guild_id, user_id, amount):
    g, u = str(guild_id), str(user_id)
    if g not in xp_data: xp_data[g] = {}
    d = xp_data[g].get(u, {"xp": 0, "level": 0})
    d["xp"] += amount
    lvl_up = False
    while d["xp"] >= xp_needed(d["level"] + 1):
        d["xp"] -= xp_needed(d["level"] + 1)
        d["level"] += 1
        lvl_up = True
    xp_data[g][u] = d
    save("xp_data.json", xp_data)
    return d, lvl_up

def xp_needed(level):
    return 100 + (level - 1) * 50

# ══════════════════════════════════════════
#  ECONOMY
# ══════════════════════════════════════════
def get_balance(user_id):
    return economy_data.get(str(user_id), {"balance": 0, "daily_streak": 0, "last_daily": None})

def set_balance(user_id, data):
    economy_data[str(user_id)] = data
    save("economy_data.json", economy_data)

# ══════════════════════════════════════════
#  EVENTS
# ══════════════════════════════════════════
@bot.event
async def on_ready():
    # Do NOT auto-sync here — use !reload instead to avoid duplicate commands
    print(f"✅ {bot.user} is online | {len(bot.guilds)} servers | Use !reload to sync slash commands")
    await bot.change_presence(activity=discord.Game(name="/help"))

async def send_welcome(member):
    ch_id = welcome_cfg.get("channel_id")
    if not ch_id: return
    ch = member.guild.get_channel(int(ch_id))
    if not ch: return
    msg = (welcome_cfg.get("message","Welcome {mention}!")
           .replace("{mention}", member.mention)
           .replace("{name}",    member.display_name)
           .replace("{server}",  member.guild.name)
           .replace("{count}",   str(member.guild.member_count)))
    embed = discord.Embed(title=welcome_cfg.get("embed_title","👋 New Member!"),
                          description=msg, color=welcome_cfg.get("embed_color",0x5865F2))
    embed.set_thumbnail(url=member.display_avatar.url)
    if welcome_cfg.get("show_member_count", True):
        embed.set_footer(text=f"Member #{member.guild.member_count}")
    await ch.send(embed=embed)

@bot.event
async def on_member_join(member):
    await send_welcome(member)
    # Auto-roles
    g = str(member.guild.id)
    for ar in autoroles.get(g, []):
        role = member.guild.get_role(ar["role_id"])
        if role: await member.add_roles(role)
    # Persistent roles
    pr = persist_roles.get(g, {}).get(str(member.id), [])
    for rid in pr:
        role = member.guild.get_role(rid)
        if role: await member.add_roles(role)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    # AFK check
    uid = str(message.author.id)
    if uid in afk_data:
        del afk_data[uid]; save("afk_data.json", afk_data)
        await message.channel.send(f"👋 Welcome back {message.author.mention}, AFK removed.", delete_after=5)
    for mention in message.mentions:
        mid = str(mention.id)
        if mid in afk_data:
            afk = afk_data[mid]
            await message.channel.send(f"💤 **{mention.display_name}** is AFK: {afk['message']}", delete_after=10)
    # Custom commands
    content = message.content.lower().strip()
    if content in custom_commands:
        await message.channel.send(custom_commands[content]); return
    # XP gain
    d, lvl_up = add_xp(message.guild.id, message.author.id, random.randint(3, 8))
    if lvl_up:
        await message.channel.send(f"🎉 {message.author.mention} leveled up to **Level {d['level']}**!")
        g = str(message.guild.id)
        if g in level_roles and str(d["level"]) in level_roles[g]:
            role = message.guild.get_role(level_roles[g][str(d["level"])])
            if role: await message.author.add_roles(role)
    await bot.process_commands(message)

# ══════════════════════════════════════════
#  SLASH COMMANDS
# ══════════════════════════════════════════

# ── WELCOME PANEL ──────────────────────────
@tree.command(name="welcome", description="⚙️ Open the welcome configuration panel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def welcome_panel(i: discord.Interaction):
    await i.response.send_message(embed=build_welcome_embed(i.guild), view=WelcomePanel(), ephemeral=True)

# ─────────────────────────────────────────
#  MODERATION
# ─────────────────────────────────────────
@tree.command(name="ban", description="🔨 Ban a member.")
@app_commands.describe(user="User to ban", reason="Reason", duration="Duration e.g. 2d", notify="DM the user")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(i, user: discord.Member, reason: str="No reason provided", duration: str=None, notify: bool=True):
    if notify:
        try: await user.send(f"🔨 You were banned from **{i.guild.name}**.\nReason: {reason}")
        except: pass
    await user.ban(reason=reason)
    log_mod(i.guild.id, "ban", user, i.user, reason)
    embed = discord.Embed(title="🔨 Member Banned", description=f"**{user}** banned.\nReason: {reason}", color=discord.Color.red())
    embed.set_footer(text=f"By {i.user}")
    await i.response.send_message(embed=embed)

@tree.command(name="unban", description="✅ Unban a user.")
@app_commands.describe(user="Username#0000 or User ID")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(i, user: str):
    async for entry in i.guild.bans():
        if str(entry.user.id) == user or str(entry.user) == user:
            await i.guild.unban(entry.user)
            log_mod(i.guild.id, "unban", entry.user, i.user, "Manual unban")
            await i.response.send_message(f"✅ **{entry.user}** unbanned."); return
    await i.response.send_message("❌ User not found in ban list.", ephemeral=True)

@tree.command(name="kick", description="👢 Kick a member.")
@app_commands.describe(member="Member to kick", reason="Reason", notify="DM the user")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(i, member: discord.Member, reason: str="No reason provided", notify: bool=True):
    if notify:
        try: await member.send(f"👢 You were kicked from **{i.guild.name}**.\nReason: {reason}")
        except: pass
    await member.kick(reason=reason)
    log_mod(i.guild.id, "kick", member, i.user, reason)
    embed = discord.Embed(title="👢 Member Kicked", description=f"**{member}** kicked.\nReason: {reason}", color=discord.Color.orange())
    embed.set_footer(text=f"By {i.user}")
    await i.response.send_message(embed=embed)

@tree.command(name="mute", description="🔇 Timeout a member.")
@app_commands.describe(member="Member", duration="Duration in minutes", reason="Reason")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(i, member: discord.Member, duration: int=10, reason: str="No reason provided"):
    await member.timeout(timedelta(minutes=duration), reason=reason)
    log_mod(i.guild.id, "mute", member, i.user, reason)
    embed = discord.Embed(title="🔇 Member Muted", description=f"**{member}** muted for {duration} min.\nReason: {reason}", color=discord.Color.yellow())
    await i.response.send_message(embed=embed)

@tree.command(name="unmute", description="🔊 Remove a member's timeout.")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(i, member: discord.Member):
    await member.timeout(None)
    await i.response.send_message(f"✅ **{member}** has been unmuted.")

@tree.command(name="softban", description="🔨 Ban and immediately unban to clear messages.")
@app_commands.checks.has_permissions(ban_members=True)
async def softban(i, member: discord.Member, reason: str="No reason provided"):
    await member.ban(reason=f"Softban: {reason}", delete_message_days=7)
    await i.guild.unban(member)
    log_mod(i.guild.id, "softban", member, i.user, reason)
    await i.response.send_message(f"🔨 **{member}** softbanned. Messages deleted.")

@tree.command(name="warn", description="⚠️ Warn a member.")
@app_commands.checks.has_permissions(kick_members=True)
async def warn_slash(i, member: discord.Member, reason: str="No reason provided"):
    g, u = str(i.guild.id), str(member.id)
    if g not in warns_data: warns_data[g] = {}
    if u not in warns_data[g]: warns_data[g][u] = []
    warns_data[g][u].append({"reason": reason, "date": str(datetime.utcnow()), "mod": str(i.user)})
    save("warns_data.json", warns_data)
    log_mod(i.guild.id, "warn", member, i.user, reason)
    try: await member.send(f"⚠️ Warning in **{i.guild.name}**: {reason}")
    except: pass
    await i.response.send_message(f"⚠️ **{member}** warned. Total: {len(warns_data[g][u])}")

@tree.command(name="warns", description="📋 View warnings of a member.")
async def warns_list(i, member: discord.Member):
    g, u = str(i.guild.id), str(member.id)
    w = warns_data.get(g, {}).get(u, [])
    if not w:
        await i.response.send_message(f"✅ {member.mention} has no warnings.", ephemeral=True); return
    embed = discord.Embed(title=f"⚠️ Warnings — {member}", color=discord.Color.orange())
    for idx, warn in enumerate(w, 1):
        embed.add_field(name=f"#{idx} — {warn['date'][:10]}", value=f"{warn['reason']} (by {warn['mod']})", inline=False)
    await i.response.send_message(embed=embed)

@tree.command(name="clearwarns", description="🗑️ Clear all warnings of a member.")
@app_commands.checks.has_permissions(kick_members=True)
async def clearwarns(i, member: discord.Member):
    g, u = str(i.guild.id), str(member.id)
    if g in warns_data and u in warns_data[g]:
        warns_data[g][u] = []
        save("warns_data.json", warns_data)
    await i.response.send_message(f"✅ Warnings cleared for {member.mention}.")

@tree.command(name="note", description="📝 Add a note to a member in mod logs.")
@app_commands.checks.has_permissions(kick_members=True)
async def note(i, member: discord.Member, note_text: str):
    log_mod(i.guild.id, "note", member, i.user, note_text)
    await i.response.send_message(f"📝 Note added for {member.mention}.", ephemeral=True)

@tree.command(name="modlogs", description="📋 View mod log for a member.")
@app_commands.checks.has_permissions(kick_members=True)
async def modlogs(i, member: discord.Member):
    g = str(i.guild.id)
    logs = [l for l in modlogs_data.get(g, []) if l["user_id"] == str(member.id)]
    if not logs:
        await i.response.send_message(f"No mod logs for {member.mention}.", ephemeral=True); return
    embed = discord.Embed(title=f"📋 Mod Logs — {member}", color=discord.Color.blurple())
    for log in logs[-10:]:
        embed.add_field(name=f"{log['type'].upper()} — {log['date'][:10]}", value=f"{log['reason']} (by {log['mod']})", inline=False)
    await i.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="modstats", description="📊 View moderation statistics of a moderator.")
@app_commands.checks.has_permissions(kick_members=True)
async def modstats(i, moderator: discord.Member):
    g = str(i.guild.id)
    logs = [l for l in modlogs_data.get(g, []) if l["mod"] == str(moderator)]
    counts = defaultdict(int)
    for l in logs: counts[l["type"]] += 1
    embed = discord.Embed(title=f"📊 Mod Stats — {moderator}", color=discord.Color.blurple())
    for action, count in counts.items():
        embed.add_field(name=action.upper(), value=str(count), inline=True)
    embed.set_footer(text=f"Total actions: {len(logs)}")
    await i.response.send_message(embed=embed)

@tree.command(name="lock", description="🔒 Lock a channel.")
@app_commands.describe(channel="Channel to lock (default: current)", reason="Reason")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(i, channel: discord.TextChannel=None, reason: str="No reason provided"):
    ch = channel or i.channel
    await ch.set_permissions(i.guild.default_role, send_messages=False)
    await i.response.send_message(f"🔒 {ch.mention} locked. Reason: {reason}")

@tree.command(name="unlock", description="🔓 Unlock a channel.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(i, channel: discord.TextChannel=None):
    ch = channel or i.channel
    await ch.set_permissions(i.guild.default_role, send_messages=None)
    await i.response.send_message(f"🔓 {ch.mention} unlocked.")

@tree.command(name="slowmode", description="🐢 Set slowmode for a channel.")
@app_commands.describe(seconds="Seconds (0 to disable)")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(i, seconds: int=0, channel: discord.TextChannel=None):
    ch = channel or i.channel
    await ch.edit(slowmode_delay=seconds)
    msg = f"🐢 Slowmode set to **{seconds}s** in {ch.mention}." if seconds else f"✅ Slowmode disabled in {ch.mention}."
    await i.response.send_message(msg)

@tree.command(name="purge", description="🗑️ Delete messages.")
@app_commands.describe(amount="Number of messages to delete")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(i, amount: int=10):
    await i.response.defer(ephemeral=True)
    deleted = await i.channel.purge(limit=amount)
    await i.followup.send(f"🗑️ {len(deleted)} message(s) deleted.", ephemeral=True)

@tree.command(name="bans", description="📋 List all banned members.")
@app_commands.checks.has_permissions(ban_members=True)
async def bans_list(i):
    bans = [entry async for entry in i.guild.bans()]
    if not bans:
        await i.response.send_message("No banned members.", ephemeral=True); return
    embed = discord.Embed(title=f"🔨 Bans ({len(bans)})", color=discord.Color.red())
    for entry in bans[:20]:
        embed.add_field(name=str(entry.user), value=entry.reason or "No reason", inline=True)
    await i.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="cases", description="📋 View active moderation cases.")
@app_commands.checks.has_permissions(kick_members=True)
async def cases(i):
    g = str(i.guild.id)
    logs = modlogs_data.get(g, [])[-15:]
    embed = discord.Embed(title="📋 Recent Mod Cases", color=discord.Color.blurple())
    for log in logs:
        embed.add_field(name=f"{log['type'].upper()} — {log['date'][:10]}", value=f"User: {log['user']} | Reason: {log['reason']}", inline=False)
    await i.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="timeout", description="⏱️ Timeout a member with optional reason.")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout_cmd(i, member: discord.Member, duration: int=10, reason: str="No reason provided"):
    await member.timeout(timedelta(minutes=duration), reason=reason)
    log_mod(i.guild.id, "timeout", member, i.user, reason)
    await i.response.send_message(f"⏱️ **{member}** timed out for {duration} min.")

@tree.command(name="untimeout", description="✅ Remove timeout from a member.")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(i, member: discord.Member):
    await member.timeout(None)
    await i.response.send_message(f"✅ **{member}** timeout removed.")

# helper
def log_mod(guild_id, action, user, mod, reason):
    g = str(guild_id)
    if g not in modlogs_data: modlogs_data[g] = []
    modlogs_data[g].append({"type": action, "user": str(user), "user_id": str(user.id),
                             "mod": str(mod), "reason": reason, "date": str(datetime.utcnow())})
    save("modlogs_data.json", modlogs_data)

# ─────────────────────────────────────────
#  AUTOMOD
# ─────────────────────────────────────────
SCAM_KEYWORDS = ["free nitro", "discord gift", "steamcommunity.com/gift", "click here to claim"]

@tree.command(name="automod_antiscam", description="🤖 Enable/disable anti-scam.")
@app_commands.describe(enabled="Enable or disable")
@app_commands.checks.has_permissions(manage_guild=True)
async def automod_scam(i, enabled: bool):
    g = str(i.guild.id)
    if g not in automod_cfg: automod_cfg[g] = {}
    automod_cfg[g]["anti_scam"] = enabled
    save("automod_config.json", automod_cfg)
    await i.response.send_message(f"🤖 Anti-scam {'enabled' if enabled else 'disabled'}.")

@bot.event
async def on_message_edit(before, after):
    await check_automod(after)

async def check_automod(message):
    if message.author.bot or not message.guild: return
    g = str(message.guild.id)
    cfg = automod_cfg.get(g, {})
    if cfg.get("anti_scam"):
        content = message.content.lower()
        if any(kw in content for kw in SCAM_KEYWORDS):
            await message.delete()
            try: await message.author.send("⚠️ Your message was removed: possible scam detected.")
            except: pass

# ─────────────────────────────────────────
#  AUTOROLES
# ─────────────────────────────────────────
@tree.command(name="autorole_add", description="➕ Add an auto role.")
@app_commands.checks.has_permissions(manage_roles=True)
async def autorole_add(i, role: discord.Role):
    g = str(i.guild.id)
    if g not in autoroles: autoroles[g] = []
    autoroles[g].append({"role_id": role.id})
    save("autoroles.json", autoroles)
    await i.response.send_message(f"✅ Auto role {role.mention} added.")

@tree.command(name="autorole_remove", description="➖ Remove an auto role.")
@app_commands.checks.has_permissions(manage_roles=True)
async def autorole_remove(i, role: discord.Role):
    g = str(i.guild.id)
    autoroles[g] = [r for r in autoroles.get(g,[]) if r["role_id"] != role.id]
    save("autoroles.json", autoroles)
    await i.response.send_message(f"✅ Auto role {role.mention} removed.")

@tree.command(name="autorole_list", description="📋 List all auto roles.")
async def autorole_list(i):
    g = str(i.guild.id)
    roles = [i.guild.get_role(r["role_id"]) for r in autoroles.get(g,[])]
    roles = [r for r in roles if r]
    embed = discord.Embed(title="➕ Auto Roles", description="\n".join(r.mention for r in roles) or "None", color=discord.Color.blurple())
    await i.response.send_message(embed=embed)

# ─────────────────────────────────────────
#  LEVELS
# ─────────────────────────────────────────
@tree.command(name="level", description="📊 Display your level rank card.")
async def level(i, user: discord.Member=None):
    member = user or i.user
    d = get_xp(i.guild.id, member.id)
    needed = xp_needed(d["level"] + 1)
    bar_len = 20
    filled  = int(bar_len * d["xp"] / needed)
    bar     = "█" * filled + "░" * (bar_len - filled)
    embed = discord.Embed(title=f"📊 {member.display_name}'s Rank", color=discord.Color.blurple())
    embed.add_field(name="Level", value=str(d["level"]), inline=True)
    embed.add_field(name="XP",    value=f"{d['xp']}/{needed}", inline=True)
    embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    await i.response.send_message(embed=embed)

@tree.command(name="levels", description="🏆 View the server leaderboard.")
async def levels(i):
    g = str(i.guild.id)
    board = sorted(xp_data.get(g, {}).items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)[:10]
    embed = discord.Embed(title="🏆 Leaderboard", color=discord.Color.gold())
    for rank, (uid, d) in enumerate(board, 1):
        member = i.guild.get_member(int(uid))
        name   = member.display_name if member else f"User {uid}"
        embed.add_field(name=f"#{rank} — {name}", value=f"Level {d['level']} | {d['xp']} XP", inline=False)
    await i.response.send_message(embed=embed)

@tree.command(name="give_xp", description="➕ Give XP to a member.")
@app_commands.describe(user="Target", amount="Amount of XP (1–10,000,000)")
@app_commands.checks.has_permissions(manage_guild=True)
async def give_xp(i, user: discord.Member, amount: int):
    amount = max(1, min(amount, 10_000_000))
    d, _ = add_xp(i.guild.id, user.id, amount)
    await i.response.send_message(f"✅ Gave {amount} XP to {user.mention}. Now Level {d['level']}.")

@tree.command(name="levelrole", description="🎖️ Set a role reward for a level.")
@app_commands.checks.has_permissions(manage_roles=True)
async def levelrole(i, level_num: int, role: discord.Role):
    g = str(i.guild.id)
    if g not in level_roles: level_roles[g] = {}
    level_roles[g][str(level_num)] = role.id
    save("level_roles.json", level_roles)
    await i.response.send_message(f"✅ {role.mention} will be awarded at Level {level_num}.")

# ─────────────────────────────────────────
#  AFK
# ─────────────────────────────────────────
@tree.command(name="afk", description="💤 Set your AFK status.")
@app_commands.describe(message="AFK message")
async def afk(i, message: str="AFK"):
    afk_data[str(i.user.id)] = {"message": message, "since": str(datetime.utcnow())}
    save("afk_data.json", afk_data)
    await i.response.send_message(f"💤 AFK set: {message}")

@tree.command(name="afk_remove", description="💤 Remove AFK status from a user.")
@app_commands.checks.has_permissions(kick_members=True)
async def afk_remove(i, user: discord.Member):
    if str(user.id) in afk_data:
        del afk_data[str(user.id)]; save("afk_data.json", afk_data)
        await i.response.send_message(f"✅ AFK removed for {user.mention}.")
    else:
        await i.response.send_message(f"{user.mention} is not AFK.", ephemeral=True)

@tree.command(name="afk_list", description="💤 List AFK members.")
async def afk_list(i):
    if not afk_data:
        await i.response.send_message("No AFK members.", ephemeral=True); return
    embed = discord.Embed(title="💤 AFK Members", color=discord.Color.greyple())
    for uid, d in list(afk_data.items())[:20]:
        member = i.guild.get_member(int(uid))
        name   = member.display_name if member else uid
        embed.add_field(name=name, value=d["message"], inline=True)
    await i.response.send_message(embed=embed)

# ─────────────────────────────────────────
#  ECONOMY
# ─────────────────────────────────────────
@tree.command(name="balance", description="👜 Display your current balance.")
async def balance(i, user: discord.Member=None):
    member = user or i.user
    d = get_balance(member.id)
    embed = discord.Embed(title=f"👜 {member.display_name}'s Balance", color=discord.Color.gold())
    embed.add_field(name="💰 Coins", value=str(d.get("balance", 0)), inline=True)
    embed.add_field(name="🔥 Daily streak", value=str(d.get("daily_streak", 0)), inline=True)
    await i.response.send_message(embed=embed)

@tree.command(name="daily", description="💰 Claim your daily reward.")
async def daily(i):
    d = get_balance(i.user.id)
    last = d.get("last_daily")
    now  = datetime.utcnow()
    if last:
        last_dt = datetime.fromisoformat(last)
        if (now - last_dt).total_seconds() < 86400:
            remaining = 86400 - (now - last_dt).total_seconds()
            h, m = int(remaining//3600), int((remaining%3600)//60)
            await i.response.send_message(f"⏳ Daily already claimed. Next in {h}h {m}m.", ephemeral=True); return
        d["daily_streak"] = d.get("daily_streak", 0) + 1 if (now - last_dt).total_seconds() < 172800 else 1
    else:
        d["daily_streak"] = 1
    reward = 100 + (d["daily_streak"] - 1) * 10
    d["balance"] = d.get("balance", 0) + reward
    d["last_daily"] = str(now)
    set_balance(i.user.id, d)
    await i.response.send_message(f"💰 Daily claimed! +**{reward}** coins | Streak: {d['daily_streak']} 🔥")

@tree.command(name="jackpot", description="💰 Display the current jackpot value.")
async def jackpot(i):
    total = sum(d.get("balance", 0) for d in economy_data.values())
    jackpot_val = max(1000, total // 10)
    await i.response.send_message(f"💰 Current Jackpot: **{jackpot_val}** coins!")

@tree.command(name="dice", description="🎲 Bet coins on a dice roll.")
@app_commands.describe(amount="Bet amount", target="Target number 2–12")
async def dice(i, amount: int, target: int):
    d = get_balance(i.user.id)
    if d.get("balance",0) < amount:
        await i.response.send_message("❌ Not enough coins.", ephemeral=True); return
    if not (2 <= target <= 12):
        await i.response.send_message("❌ Target must be 2–12.", ephemeral=True); return
    roll = random.randint(1,6) + random.randint(1,6)
    win  = roll == target
    d["balance"] = d.get("balance",0) + (amount * 2 if win else -amount)
    set_balance(i.user.id, d)
    embed = discord.Embed(title="🎲 Dice Roll", color=discord.Color.green() if win else discord.Color.red())
    embed.add_field(name="Rolled", value=str(roll), inline=True)
    embed.add_field(name="Target", value=str(target), inline=True)
    embed.add_field(name="Result", value="WIN 🎉" if win else "LOSE 💸", inline=True)
    embed.set_footer(text=f"Balance: {d['balance']} coins")
    await i.response.send_message(embed=embed)

@tree.command(name="casino", description="🎰 Bet coins in the casino.")
@app_commands.describe(amount="Bet (250+ for jackpot chance)")
async def casino(i, amount: int):
    d = get_balance(i.user.id)
    if d.get("balance",0) < amount:
        await i.response.send_message("❌ Not enough coins.", ephemeral=True); return
    roll = random.random()
    if roll < 0.02 and amount >= 250:
        mult, label = 10, "🎰 JACKPOT!!!"
    elif roll < 0.3:
        mult, label = 2, "🎉 Win!"
    elif roll < 0.5:
        mult, label = 1.5, "✅ Small win"
    else:
        mult, label = 0, "💸 Lost"
    winnings = int(amount * mult) - amount
    d["balance"] = d.get("balance",0) + winnings
    set_balance(i.user.id, d)
    embed = discord.Embed(title=label, color=discord.Color.gold() if winnings >= 0 else discord.Color.red())
    embed.add_field(name="Bet", value=str(amount), inline=True)
    embed.add_field(name="Result", value=f"+{winnings}" if winnings >= 0 else str(winnings), inline=True)
    embed.set_footer(text=f"Balance: {d['balance']} coins")
    await i.response.send_message(embed=embed)

# ─────────────────────────────────────────
#  SOCIAL
# ─────────────────────────────────────────
INTERACT_GIFS = {
    "kiss":    "https://media.tenor.com/5HNS-thUYUkAAAAC/anime-kiss.gif",
    "hug":     "https://media.tenor.com/e1BaQlpv_cQAAAAC/anime-hug.gif",
    "slap":    "https://media.tenor.com/pxCRFR2a0TQAAAAC/anime-slap.gif",
    "pat":     "https://media.tenor.com/MepiHIYOFnQAAAAC/head-pat.gif",
    "punch":   "https://media.tenor.com/CFpvFwQV-SsAAAAC/punch-anime.gif",
    "cuddle":  "https://media.tenor.com/AZVJuiNVNXoAAAAC/cuddle-anime.gif",
    "bite":    "https://media.tenor.com/c3OVZ4JEf3QAAAAC/anime-bite.gif",
    "poke":    "https://media.tenor.com/L_r1-RCUoxYAAAAC/anime-poke.gif",
    "dance":   "https://media.tenor.com/IhNTJdx_KZEAAAAC/anime-dance.gif",
    "tickle":  "https://media.tenor.com/7-VcAkuT-WMAAAAC/tickle.gif",
    "highfive":"https://media.tenor.com/WCzVQnuA3LgAAAAC/high-five-anime.gif",
    "feed":    "https://media.tenor.com/fUqsTBOIPzMAAAAC/anime-feed.gif",
    "greet":   "https://media.tenor.com/EHEnCFWsAYMAAAAC/wave-hello.gif",
    "wasted":  "https://media.tenor.com/pqMBHy3N7KQAAAAC/wasted-gta.gif",
    "stare":   "https://media.tenor.com/TFGjhf0-XcUAAAAC/anime-stare.gif",
    "smug":    "https://media.tenor.com/X_9h7JcmDi8AAAAC/smug-anime.gif",
    "blush":   "https://media.tenor.com/DKhd-Y_W1MoAAAAC/anime-blush.gif",
    "cry":     "https://media.tenor.com/yoEHGqGl7PYAAAAC/anime-cry.gif",
}

async def interact_cmd(i: discord.Interaction, action: str, user: discord.Member):
    gif = INTERACT_GIFS.get(action, "")
    embed = discord.Embed(
        description=f"**{i.user.display_name}** {action}s **{user.display_name}**! {'💕' if action in ['kiss','cuddle','hug'] else ''}",
        color=discord.Color.pink()
    )
    if gif: embed.set_image(url=gif)
    await i.response.send_message(embed=embed)

@tree.command(name="kiss",      description="😘 Kiss someone.") 
async def kiss(i, user: discord.Member):     await interact_cmd(i, "kiss", user)
@tree.command(name="hug",       description="🤗 Hug someone.")  
async def hug(i, user: discord.Member):      await interact_cmd(i, "hug", user)
@tree.command(name="slap",      description="✋ Slap someone.")  
async def slap(i, user: discord.Member):     await interact_cmd(i, "slap", user)
@tree.command(name="pat",       description="✋ Pat someone.")   
async def pat(i, user: discord.Member):      await interact_cmd(i, "pat", user)
@tree.command(name="punch",     description="👊 Punch someone.") 
async def punch(i, user: discord.Member):    await interact_cmd(i, "punch", user)
@tree.command(name="cuddle",    description="🫂 Cuddle someone.")
async def cuddle(i, user: discord.Member):   await interact_cmd(i, "cuddle", user)
@tree.command(name="bite",      description="😬 Bite someone.")  
async def bite(i, user: discord.Member):     await interact_cmd(i, "bite", user)
@tree.command(name="poke",      description="👉 Poke someone.")  
async def poke(i, user: discord.Member):     await interact_cmd(i, "poke", user)
@tree.command(name="dance",     description="💃 Dance with someone.") 
async def dance(i, user: discord.Member):    await interact_cmd(i, "dance", user)
@tree.command(name="tickle",    description="👆 Tickle someone.")
async def tickle(i, user: discord.Member):   await interact_cmd(i, "tickle", user)
@tree.command(name="highfive",  description="🤚 Highfive someone.") 
async def highfive(i, user: discord.Member): await interact_cmd(i, "highfive", user)
@tree.command(name="feed",      description="🍖 Feed someone.")  
async def feed(i, user: discord.Member):     await interact_cmd(i, "feed", user)
@tree.command(name="greet",     description="👋 Greet someone.")
async def greet(i, user: discord.Member):    await interact_cmd(i, "greet", user)
@tree.command(name="wasted",    description="😵 Make someone wasted.")
async def wasted(i, user: discord.Member):   await interact_cmd(i, "wasted", user)
@tree.command(name="stare",     description="👀 Stare at someone.")
async def stare(i, user: discord.Member):    await interact_cmd(i, "stare", user)
@tree.command(name="smug",      description="😏 Smug at someone.")
async def smug(i, user: discord.Member):     await interact_cmd(i, "smug", user)
@tree.command(name="blush",     description="😊 Blush at someone.")
async def blush(i, user: discord.Member):    await interact_cmd(i, "blush", user)
@tree.command(name="cry",       description="😢 Cry at someone.")
async def cry(i, user: discord.Member):      await interact_cmd(i, "cry", user)

# ─────────────────────────────────────────
#  MARRIAGE & FAMILY
# ─────────────────────────────────────────
@tree.command(name="marry", description="💍 Propose to a user.")
async def marry(i, member: discord.Member):
    if member.id == i.user.id:
        await i.response.send_message("❌ You can't marry yourself.", ephemeral=True); return
    embed = discord.Embed(description=f"💍 {i.user.mention} proposes to {member.mention}!\nType `!accept` to accept.", color=discord.Color.pink())
    await i.response.send_message(embed=embed)
    def check(m): return m.author == member and m.content.lower() == "!accept"
    try:
        await bot.wait_for("message", check=check, timeout=60)
        u1, u2 = str(i.user.id), str(member.id)
        marriages.setdefault(u1, [])
        marriages.setdefault(u2, [])
        if u2 not in marriages[u1]: marriages[u1].append(u2)
        if u1 not in marriages[u2]: marriages[u2].append(u1)
        save("marriages.json", marriages)
        await i.channel.send(f"💍 Congratulations! **{i.user.display_name}** and **{member.display_name}** are now married! 🎉")
    except asyncio.TimeoutError:
        await i.channel.send(f"💔 {member.mention} did not respond in time.")

@tree.command(name="divorce", description="💔 Divorce a user.")
async def divorce(i, user: discord.Member):
    u1, u2 = str(i.user.id), str(user.id)
    if u2 in marriages.get(u1, []):
        marriages[u1].remove(u2)
        if u1 in marriages.get(u2, []): marriages[u2].remove(u1)
        save("marriages.json", marriages)
        await i.response.send_message(f"💔 **{i.user.display_name}** and **{user.display_name}** are now divorced.")
    else:
        await i.response.send_message("❌ You are not married to this user.", ephemeral=True)

@tree.command(name="marriages", description="💍 View your marriages.")
async def marriages_list(i, user: discord.Member=None):
    member = user or i.user
    m_list = marriages.get(str(member.id), [])
    if not m_list:
        await i.response.send_message(f"{member.mention} is not married to anyone.", ephemeral=True); return
    partners = [i.guild.get_member(int(uid)) for uid in m_list]
    names    = [p.display_name if p else uid for p, uid in zip(partners, m_list)]
    embed = discord.Embed(title=f"💍 {member.display_name}'s Marriages", description="\n".join(names), color=discord.Color.pink())
    await i.response.send_message(embed=embed)

@tree.command(name="adopt", description="👶 Adopt a user.")
async def adopt(i, member: discord.Member):
    f = families.setdefault(str(i.user.id), {"parent": None, "children": []})
    f["children"].append(str(member.id))
    families.setdefault(str(member.id), {"parent": None, "children": []})["parent"] = str(i.user.id)
    save("families.json", families)
    await i.response.send_message(f"👶 {i.user.mention} adopted {member.mention}!")

@tree.command(name="disown", description="💔 Disown one of your adopted children.")
async def disown(i: discord.Interaction, member: discord.Member):
    uid = str(i.user.id)
    cid = str(member.id)
    f   = families.get(uid, {"parent": None, "children": []})
    if cid not in f.get("children", []):
        await i.response.send_message(f"❌ {member.mention} is not your child.", ephemeral=True); return
    f["children"].remove(cid)
    families[uid] = f
    # Remove parent reference from child
    if cid in families:
        families[cid]["parent"] = None
    save("families.json", families)
    await i.response.send_message(f"💔 You have disowned **{member.display_name}**.")

@tree.command(name="family_tree", description="🌳 View a family tree.")
async def family_tree(i, user: discord.Member=None):
    member = user or i.user
    f = families.get(str(member.id), {"parent": None, "children": []})
    embed = discord.Embed(title=f"🌳 {member.display_name}'s Family", color=discord.Color.green())
    parent_id = f.get("parent")
    if parent_id:
        p = i.guild.get_member(int(parent_id))
        embed.add_field(name="👪 Parent", value=p.display_name if p else parent_id, inline=False)
    children = [i.guild.get_member(int(c)) for c in f.get("children",[])]
    if children:
        embed.add_field(name="👶 Children", value="\n".join(c.display_name if c else "Unknown" for c in children), inline=False)
    await i.response.send_message(embed=embed)

# ─────────────────────────────────────────
#  LOVE CALC
# ─────────────────────────────────────────
@tree.command(name="lovecalc", description="💗 Calculate love percentage between two users.")
async def lovecalc(i, user1: discord.Member, user2: discord.Member=None):
    target = user2 or i.user
    key    = f"{min(user1.id, target.id)}_{max(user1.id, target.id)}"
    if key not in lovecalcs:
        lovecalcs[key] = random.randint(0, 100)
        save("lovecalcs.json", lovecalcs)
    pct = lovecalcs[key]
    bar = "❤️" * (pct // 10) + "🖤" * (10 - pct // 10)
    embed = discord.Embed(title="💗 Love Calculator", color=discord.Color.pink())
    embed.add_field(name="Couple", value=f"{user1.display_name} & {target.display_name}", inline=False)
    embed.add_field(name=f"{pct}%", value=bar, inline=False)
    await i.response.send_message(embed=embed)

# ─────────────────────────────────────────
#  FUN
# ─────────────────────────────────────────
@tree.command(name="8ball", description="🎱 Ask the magic 8ball.")
async def ball8(i, question: str):
    answers = ["Yes.", "No.", "Maybe.", "Definitely!", "Absolutely not.", "Ask again later.",
               "Without a doubt.", "Don't count on it.", "Signs point to yes.", "My sources say no."]
    embed = discord.Embed(title="🎱 Magic 8Ball", color=discord.Color.dark_purple())
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer",   value=random.choice(answers), inline=False)
    await i.response.send_message(embed=embed)

@tree.command(name="coinflip", description="🪙 Flip a coin.")
async def coinflip(i, bet: str=None):
    result = random.choice(["Heads", "Tails"])
    won    = bet and bet.lower() in result.lower()
    embed  = discord.Embed(title=f"🪙 {result}!", color=discord.Color.gold())
    if bet: embed.set_footer(text="✅ You won!" if won else "❌ You lost!")
    await i.response.send_message(embed=embed)

@tree.command(name="choose", description="🤔 Let the bot make a choice for you.")
@app_commands.describe(choices="Options separated by commas")
async def choose(i, choices: str):
    opts = [c.strip() for c in choices.split(",") if c.strip()]
    if not opts:
        await i.response.send_message("❌ Provide at least one option.", ephemeral=True); return
    await i.response.send_message(f"🤔 I choose: **{random.choice(opts)}**")

@tree.command(name="roulette", description="🥇 Get a random winner from server members.")
async def roulette(i, title: str="Winner"):
    members = [m for m in i.guild.members if not m.bot]
    winner  = random.choice(members)
    await i.response.send_message(f"🎰 **{title}**: {winner.mention} wins! 🎉")

@tree.command(name="mixnames", description="🔀 Mix two usernames together.")
async def mixnames(i, user1: discord.Member, user2: discord.Member):
    n1, n2  = user1.display_name, user2.display_name
    mixed   = n1[:len(n1)//2] + n2[len(n2)//2:]
    await i.response.send_message(f"🔀 Mixed name: **{mixed}**")

@tree.command(name="maths", description="👩‍🏫 Execute a mathematical calculation.")
async def maths(i, calculation: str):
    try:
        allowed = set("0123456789+-*/().% ")
        if not all(c in allowed for c in calculation):
            raise ValueError("Invalid characters")
        result = eval(calculation, {"__builtins__": {}})
        await i.response.send_message(f"🧮 `{calculation}` = **{result}**")
    except:
        await i.response.send_message("❌ Invalid calculation.", ephemeral=True)

@tree.command(name="define", description="📖 Define a word.")
async def define(i, word: str):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}") as r:
            if r.status != 200:
                await i.response.send_message(f"❌ No definition found for **{word}**.", ephemeral=True); return
            data = await r.json()
            meaning = data[0]["meanings"][0]["definitions"][0]["definition"]
            embed = discord.Embed(title=f"📖 {word}", description=meaning, color=discord.Color.blurple())
            await i.response.send_message(embed=embed)

@tree.command(name="letter", description="💌 Send a love letter to someone.")
async def letter(i, member: discord.Member, message: str="Thinking of you 💕"):
    embed = discord.Embed(title="💌 Love Letter", description=f"*{message}*", color=discord.Color.pink())
    embed.set_footer(text=f"From {i.user.display_name} to {member.display_name}")
    await i.response.send_message(f"{member.mention}", embed=embed)

# ─────────────────────────────────────────
#  ANIMALS
# ─────────────────────────────────────────
ANIMAL_APIS = {
    "cat":   "https://api.thecatapi.com/v1/images/search",
    "dog":   "https://dog.ceo/api/breeds/image/random",
    "fox":   "https://randomfox.ca/floof/",
    "duck":  "https://random-d.uk/api/random",
}

async def fetch_animal(animal: str):
    try:
        async with aiohttp.ClientSession() as s:
            if animal == "cat":
                async with s.get(ANIMAL_APIS["cat"]) as r:
                    return (await r.json())[0]["url"]
            elif animal == "dog":
                async with s.get(ANIMAL_APIS["dog"]) as r:
                    return (await r.json())["message"]
            elif animal == "fox":
                async with s.get(ANIMAL_APIS["fox"]) as r:
                    return (await r.json())["image"]
            elif animal == "duck":
                async with s.get(ANIMAL_APIS["duck"]) as r:
                    return (await r.json())["url"]
    except:
        return None

@tree.command(name="cat",  description="🐱 Send a random cat picture.")
async def cat(i):
    url = await fetch_animal("cat")
    embed = discord.Embed(title="🐱 Random Cat!", color=discord.Color.orange())
    if url: embed.set_image(url=url)
    await i.response.send_message(embed=embed)

@tree.command(name="dog",  description="🐶 Send a random dog picture.")
async def dog(i):
    url = await fetch_animal("dog")
    embed = discord.Embed(title="🐶 Random Dog!", color=discord.Color.brown())
    if url: embed.set_image(url=url)
    await i.response.send_message(embed=embed)

@tree.command(name="fox",  description="🦊 Send a random fox picture.")
async def fox(i):
    url = await fetch_animal("fox")
    embed = discord.Embed(title="🦊 Random Fox!", color=discord.Color.orange())
    if url: embed.set_image(url=url)
    await i.response.send_message(embed=embed)

@tree.command(name="duck", description="🦆 Send a random duck picture.")
async def duck(i):
    url = await fetch_animal("duck")
    embed = discord.Embed(title="🦆 Random Duck!", color=discord.Color.green())
    if url: embed.set_image(url=url)
    await i.response.send_message(embed=embed)

@tree.command(name="bird", description="🐦 Send a random bird picture.")
async def bird(i):
    async with aiohttp.ClientSession() as s:
        async with s.get("https://some-random-api.com/animal/bird") as r:
            if r.status == 200:
                data = await r.json()
                embed = discord.Embed(title="🐦 Random Bird!", color=discord.Color.blue())
                embed.set_image(url=data.get("image",""))
                await i.response.send_message(embed=embed)
            else:
                await i.response.send_message("🐦 Here's a birb! 🐦 (API unavailable)", ephemeral=True)

# ─────────────────────────────────────────
#  INFO
# ─────────────────────────────────────────
@tree.command(name="avatar", description="🖼️ Display a user's avatar.")
async def avatar(i, user: discord.Member=None):
    member = user or i.user
    embed  = discord.Embed(title=f"🖼️ {member.display_name}'s Avatar", color=discord.Color.blurple())
    embed.set_image(url=member.display_avatar.url)
    await i.response.send_message(embed=embed)

@tree.command(name="banner", description="🌇 Display a user's banner.")
async def banner(i, user: discord.Member=None):
    member = user or i.user
    fetched = await bot.fetch_user(member.id)
    if fetched.banner:
        embed = discord.Embed(title=f"🌇 {member.display_name}'s Banner", color=discord.Color.blurple())
        embed.set_image(url=fetched.banner.url)
        await i.response.send_message(embed=embed)
    else:
        await i.response.send_message(f"❌ {member.display_name} has no banner.", ephemeral=True)

@tree.command(name="userinfo", description="ℹ️ Display info about a user.")
async def userinfo(i, user: discord.Member=None):
    member = user or i.user
    embed  = discord.Embed(title=f"ℹ️ {member}", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID",         value=str(member.id), inline=True)
    embed.add_field(name="Joined",     value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "N/A", inline=True)
    embed.add_field(name="Created",    value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Roles",      value=" ".join(r.mention for r in member.roles[1:]) or "None", inline=False)
    await i.response.send_message(embed=embed)

@tree.command(name="serverinfo", description="ℹ️ Display info about this server.")
async def serverinfo(i):
    g = i.guild
    embed = discord.Embed(title=f"ℹ️ {g.name}", color=discord.Color.blurple())
    if g.icon: embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="Owner",    value=str(g.owner), inline=True)
    embed.add_field(name="Members",  value=str(g.member_count), inline=True)
    embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
    embed.add_field(name="Roles",    value=str(len(g.roles)), inline=True)
    embed.add_field(name="Created",  value=g.created_at.strftime("%Y-%m-%d"), inline=True)
    await i.response.send_message(embed=embed)

@tree.command(name="roleinfo", description="ℹ️ Display info about a role.")
async def roleinfo(i, role: discord.Role):
    embed = discord.Embed(title=f"ℹ️ {role.name}", color=role.color)
    embed.add_field(name="ID",      value=str(role.id), inline=True)
    embed.add_field(name="Members", value=str(len(role.members)), inline=True)
    embed.add_field(name="Color",   value=str(role.color), inline=True)
    embed.add_field(name="Mentionable", value=str(role.mentionable), inline=True)
    await i.response.send_message(embed=embed)

@tree.command(name="ping", description="🏓 Check bot latency.")
async def ping(i):
    await i.response.send_message(f"🏓 Pong! Latency: **{round(bot.latency * 1000)}ms**")

# ─────────────────────────────────────────
#  UTILITY
# ─────────────────────────────────────────
@tree.command(name="checklist_add", description="📑 Add items to your checklist.")
@app_commands.describe(items="Items separated by commas")
async def checklist_add(i, items: str):
    uid = str(i.user.id)
    checklist_data.setdefault(uid, [])
    new_items = [item.strip() for item in items.split(",") if item.strip()]
    checklist_data[uid].extend(new_items)
    save("checklist_data.json", checklist_data)
    await i.response.send_message(f"✅ Added {len(new_items)} item(s) to your checklist.", ephemeral=True)

@tree.command(name="checklist_view", description="📑 View your checklist.")
async def checklist_view(i):
    uid = str(i.user.id)
    items = checklist_data.get(uid, [])
    if not items:
        await i.response.send_message("📭 Your checklist is empty.", ephemeral=True); return
    embed = discord.Embed(title="📑 Your Checklist", color=discord.Color.blurple())
    embed.description = "\n".join(f"• {item}" for item in items)
    await i.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="checklist_remove", description="📑 Remove an item from your checklist.")
@app_commands.describe(item="Exact item text to remove")
async def checklist_remove(i, item: str):
    uid = str(i.user.id)
    if item in checklist_data.get(uid, []):
        checklist_data[uid].remove(item)
        save("checklist_data.json", checklist_data)
        await i.response.send_message(f"🗑️ Removed: {item}", ephemeral=True)
    else:
        await i.response.send_message("❌ Item not found.", ephemeral=True)

@tree.command(name="checklist_reset", description="📑 Reset your entire checklist.")
async def checklist_reset(i):
    checklist_data[str(i.user.id)] = []
    save("checklist_data.json", checklist_data)
    await i.response.send_message("✅ Checklist reset.", ephemeral=True)

@tree.command(name="emoji_add", description="😀 Add an emoji to the server.")
@app_commands.describe(name="Emoji name", link="Image URL")
@app_commands.checks.has_permissions(manage_expressions=True)
async def emoji_add(i, name: str, link: str):
    async with aiohttp.ClientSession() as s:
        async with s.get(link) as r:
            data = await r.read()
    emoji = await i.guild.create_custom_emoji(name=name, image=data)
    await i.response.send_message(f"✅ Emoji {emoji} added!")

@tree.command(name="emoji_delete", description="😀 Delete a server emoji.")
@app_commands.checks.has_permissions(manage_expressions=True)
async def emoji_delete(i, name: str):
    emoji = discord.utils.get(i.guild.emojis, name=name)
    if emoji:
        await emoji.delete()
        await i.response.send_message(f"🗑️ Emoji `{name}` deleted.")
    else:
        await i.response.send_message("❌ Emoji not found.", ephemeral=True)

@tree.command(name="emoji_list", description="😀 List all server emojis.")
async def emoji_list(i):
    emojis = i.guild.emojis
    embed  = discord.Embed(title=f"😀 Server Emojis ({len(emojis)})", color=discord.Color.blurple())
    embed.description = " ".join(str(e) for e in emojis[:50]) or "No emojis."
    await i.response.send_message(embed=embed)

@tree.command(name="language", description="🌐 Set the server language.")
@app_commands.checks.has_permissions(manage_guild=True)
async def language(i, lang: str):
    await i.response.send_message(f"🌐 Server language set to **{lang}**. (Stored for reference)")

# ─────────────────────────────────────────
#  PERSISTENT ROLES
# ─────────────────────────────────────────
@tree.command(name="persistrole_add", description="💾 Save a member's current roles to persist on rejoin.")
@app_commands.checks.has_permissions(manage_roles=True)
async def persistrole_add(i, member: discord.Member):
    g = str(i.guild.id)
    persist_roles.setdefault(g, {})[str(member.id)] = [r.id for r in member.roles[1:]]
    save("persist_roles.json", persist_roles)
    await i.response.send_message(f"✅ Roles saved for {member.mention}. They'll be restored on rejoin.")

# ─────────────────────────────────────────
#  CUSTOM COMMANDS (prefix)
# ─────────────────────────────────────────
@tree.command(name="addcmd", description="➕ Add a custom command.")
@app_commands.describe(trigger="Trigger word", response="Bot response")
@app_commands.checks.has_permissions(manage_guild=True)
async def addcmd(i, trigger: str, response: str):
    custom_commands[trigger.lower()] = response
    save("custom_commands.json", custom_commands)
    await i.response.send_message(f"✅ Command `{trigger}` added.", ephemeral=True)

@tree.command(name="delcmd", description="➖ Delete a custom command.")
@app_commands.checks.has_permissions(manage_guild=True)
async def delcmd(i, trigger: str):
    if trigger.lower() in custom_commands:
        del custom_commands[trigger.lower()]
        save("custom_commands.json", custom_commands)
        await i.response.send_message(f"🗑️ Command `{trigger}` deleted.", ephemeral=True)
    else:
        await i.response.send_message("❌ Command not found.", ephemeral=True)

@tree.command(name="listcmd", description="📋 List all custom commands.")
async def listcmd(i):
    if not custom_commands:
        await i.response.send_message("📭 No custom commands.", ephemeral=True); return
    embed = discord.Embed(title="📋 Custom Commands", color=discord.Color.blurple())
    embed.description = "\n".join(f"• `{k}` → {v}" for k, v in custom_commands.items())
    await i.response.send_message(embed=embed, ephemeral=True)

# ─────────────────────────────────────────
#  HELP
# ─────────────────────────────────────────
HELP_CATEGORIES = {
    "🛡️ Moderation":   ["/ban", "/unban", "/kick", "/mute", "/unmute", "/softban", "/warn", "/warns",
                          "/clearwarns", "/note", "/modlogs", "/modstats", "/cases", "/lock", "/unlock",
                          "/slowmode", "/purge", "/bans", "/timeout", "/untimeout"],
    "📊 Levels":        ["/level", "/levels", "/give_xp", "/levelrole"],
    "💰 Economy":       ["/balance", "/daily", "/jackpot", "/dice", "/casino"],
    "💕 Social":        ["/kiss", "/hug", "/slap", "/pat", "/punch", "/cuddle", "/bite", "/poke",
                          "/dance", "/tickle", "/highfive", "/feed", "/greet", "/wasted", "/stare",
                          "/smug", "/blush", "/cry", "/marry", "/divorce", "/marriages", "/lovecalc",
                          "/adopt", "/family_tree", "/letter"],
    "🎮 Fun":           ["/8ball", "/coinflip", "/choose", "/roulette", "/mixnames", "/maths", "/define"],
    "🐾 Animals":       ["/cat", "/dog", "/fox", "/duck", "/bird"],
    "ℹ️ Info":          ["/avatar", "/banner", "/userinfo", "/serverinfo", "/roleinfo", "/ping"],
    "⚙️ Admin":         ["/welcome", "/autorole_add", "/autorole_remove", "/autorole_list",
                          "/automod_antiscam", "/persistrole_add", "/language"],
    "💤 AFK":           ["/afk", "/afk_remove", "/afk_list"],
    "📑 Checklist":     ["/checklist_add", "/checklist_view", "/checklist_remove", "/checklist_reset"],
    "😀 Emoji":         ["/emoji_add", "/emoji_delete", "/emoji_list"],
    "💬 Custom Cmds":   ["/addcmd", "/delcmd", "/listcmd"],
}

@tree.command(name="help", description="❓ View all commands.")
@app_commands.describe(category="Category name (optional)")
async def help_cmd(i, category: str=None):
    if category:
        cat = next((v for k, v in HELP_CATEGORIES.items() if category.lower() in k.lower()), None)
        if cat:
            embed = discord.Embed(title=f"Help — {category}", description="\n".join(cat), color=discord.Color.blurple())
            await i.response.send_message(embed=embed, ephemeral=True); return
    embed = discord.Embed(title="❓ Help — All Categories", color=discord.Color.blurple())
    for cat, cmds in HELP_CATEGORIES.items():
        embed.add_field(name=cat, value=f"{len(cmds)} commands", inline=True)
    embed.set_footer(text="Use /help category:<name> for details")
    await i.response.send_message(embed=embed, ephemeral=True)

# ─────────────────────────────────────────
# ─────────────────────────────────────────
#  OWNER-ONLY ADMIN COMMAND  (!admin)
#  Secured by Discord User ID — only YOU can use it
# ─────────────────────────────────────────
@bot.command(name="admin")
async def admin_panel(ctx, action: str = "help", *, args: str = ""):
    """Owner-only admin panel. Usage: !admin <action>"""
    if ctx.author.id != OWNER_ID:
        await ctx.message.delete()
        await ctx.send("⛔ Access denied.", delete_after=3)
        return

    # ── actions ──────────────────────────
    if action == "help":
        embed = discord.Embed(title="🛡️ Admin Panel", color=discord.Color.dark_red())
        embed.add_field(name="!admin help",                    value="Show this panel", inline=False)
        embed.add_field(name="!admin serverinfo",              value="Full server stats", inline=False)
        embed.add_field(name="!admin dm <@user> <message>",    value="DM any user", inline=False)
        embed.add_field(name="!admin say <#channel> <text>",   value="Send a message as the bot", inline=False)
        embed.add_field(name="!admin embed <#channel> <text>", value="Send an embed as the bot", inline=False)
        embed.add_field(name="!admin clearwarns <@user>",      value="Wipe all warnings", inline=False)
        embed.add_field(name="!admin givemoney <@user> <amt>", value="Give coins to anyone", inline=False)
        embed.add_field(name="!admin setlevel <@user> <lvl>",  value="Set someone's level", inline=False)
        embed.add_field(name="!admin announce <text>",         value="Announce in every channel named #announcements", inline=False)
        embed.add_field(name="!admin shutdown",                value="Shut the bot down", inline=False)
        embed.set_footer(text="Only visible to you")
        await ctx.send(embed=embed)

    elif action == "serverinfo":
        g = ctx.guild
        embed = discord.Embed(title=f"🛡️ Admin — {g.name}", color=discord.Color.dark_red())
        embed.add_field(name="Members",  value=str(g.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
        embed.add_field(name="Roles",    value=str(len(g.roles)), inline=True)
        embed.add_field(name="Owner",    value=str(g.owner), inline=True)
        embed.add_field(name="Boosts",   value=str(g.premium_subscription_count), inline=True)
        embed.add_field(name="Created",  value=g.created_at.strftime("%Y-%m-%d"), inline=True)
        await ctx.send(embed=embed)

    elif action == "dm":
        parts = args.split(" ", 1)
        if len(parts) < 2 or not ctx.message.mentions:
            await ctx.send("❌ Usage: !admin dm @user message", delete_after=5); return
        target, message = ctx.message.mentions[0], parts[1]
        try:
            await target.send(message)
            await ctx.send(f"✅ DM sent to {target.mention}.", delete_after=5)
        except discord.Forbidden:
            await ctx.send(f"❌ Cannot DM {target.mention}.", delete_after=5)

    elif action == "say":
        parts = args.split(" ", 1)
        channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
        text = parts[1] if len(parts) > 1 else parts[0]
        await channel.send(text)
        await ctx.message.delete()

    elif action == "embed":
        parts = args.split(" ", 1)
        channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
        text = parts[1] if len(parts) > 1 else parts[0]
        embed = discord.Embed(description=text, color=discord.Color.blurple())
        await channel.send(embed=embed)
        await ctx.message.delete()

    elif action == "clearwarns":
        if not ctx.message.mentions:
            await ctx.send("❌ Mention a user.", delete_after=5); return
        target = ctx.message.mentions[0]
        g, u = str(ctx.guild.id), str(target.id)
        if g in warns_data and u in warns_data[g]:
            warns_data[g][u] = []
            save("warns_data.json", warns_data)
        await ctx.send(f"✅ Warnings cleared for {target.mention}.", delete_after=5)

    elif action == "givemoney":
        parts = args.split()
        if not ctx.message.mentions or len(parts) < 2:
            await ctx.send("❌ Usage: !admin givemoney @user amount", delete_after=5); return
        target = ctx.message.mentions[0]
        try:
            amount = int(parts[-1])
            d = get_balance(target.id)
            d["balance"] = d.get("balance", 0) + amount
            set_balance(target.id, d)
            await ctx.send(f"✅ Gave **{amount}** coins to {target.mention}. New balance: {d['balance']}.", delete_after=5)
        except ValueError:
            await ctx.send("❌ Amount must be a number.", delete_after=5)

    elif action == "setlevel":
        parts = args.split()
        if not ctx.message.mentions or len(parts) < 2:
            await ctx.send("❌ Usage: !admin setlevel @user level", delete_after=5); return
        target = ctx.message.mentions[0]
        try:
            lvl = int(parts[-1])
            g, u = str(ctx.guild.id), str(target.id)
            if g not in xp_data: xp_data[g] = {}
            xp_data[g][u] = {"xp": 0, "level": lvl}
            save("xp_data.json", xp_data)
            await ctx.send(f"✅ {target.mention} is now Level {lvl}.", delete_after=5)
        except ValueError:
            await ctx.send("❌ Level must be a number.", delete_after=5)

    elif action == "announce":
        if not args:
            await ctx.send("❌ Usage: !admin announce <text>", delete_after=5); return
        sent = 0
        for ch in ctx.guild.text_channels:
            if "announce" in ch.name.lower():
                embed = discord.Embed(description=args, color=discord.Color.blurple())
                embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
                await ch.send(embed=embed)
                sent += 1
        await ctx.send(f"✅ Announced in {sent} channel(s).", delete_after=5)

    elif action == "shutdown":
        await ctx.send("🔴 Shutting down...")
        await bot.close()

    else:
        await ctx.send(f"❌ Unknown action . Use .", delete_after=5)


# ─────────────────────────────────────────
#  GIVEAWAY SYSTEM
# ─────────────────────────────────────────
import re as _re

# Active giveaways: {message_id: {prize, channel_id, end_time, entries, winner_id, claim_deadline, prize_code}}
active_giveaways = {}

def parse_duration(s: str) -> int:
    """Convert e.g. '1h', '30m', '2d' to seconds."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = _re.fullmatch(r"(\d+)([smhd])", s.strip().lower())
    if not match:
        return 0
    return int(match.group(1)) * units[match.group(2)]

class GiveawayClaimView(ui.View):
    def __init__(self, giveaway_msg_id: int):
        super().__init__(timeout=None)
        self.giveaway_msg_id = giveaway_msg_id

    @ui.button(label="🎁 Claim Prize", style=discord.ButtonStyle.success, custom_id="gw_claim")
    async def claim(self, interaction: discord.Interaction, button: ui.Button):
        gw = active_giveaways.get(self.giveaway_msg_id)
        if not gw:
            await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
            return
        if interaction.user.id != gw.get("winner_id"):
            await interaction.response.send_message("❌ You are not the winner of this giveaway.", ephemeral=True)
            return
        code = gw.get("prize_code", "No code set — contact an admin.")
        try:
            await interaction.user.send(
                f"🎉 Congratulations! Here is your prize for **{gw['prize']}**:\n`{code}`"
            )
            await interaction.response.send_message("✅ Prize sent to your DMs!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ I can\'t DM you. Enable DMs and contact an admin.", ephemeral=True
            )
        button.disabled = True
        gw["claimed"] = True
        await interaction.message.edit(view=self)

class GiveawayJoinView(ui.View):
    def __init__(self, giveaway_msg_id: int):
        super().__init__(timeout=None)
        self.giveaway_msg_id = giveaway_msg_id

    @ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.primary, custom_id="gw_enter")
    async def enter(self, interaction: discord.Interaction, button: ui.Button):
        gw = active_giveaways.get(self.giveaway_msg_id)
        if not gw:
            await interaction.response.send_message("❌ This giveaway no longer exists.", ephemeral=True)
            return
        uid = interaction.user.id
        if uid in gw["entries"]:
            gw["entries"].remove(uid)
            await interaction.response.send_message("❌ You left the giveaway.", ephemeral=True)
        else:
            gw["entries"].append(uid)
            await interaction.response.send_message(f"✅ You entered! Total entries: {len(gw['entries'])}", ephemeral=True)
        # Update embed entry count
        ch = bot.get_channel(gw["channel_id"])
        if ch:
            try:
                msg = await ch.fetch_message(self.giveaway_msg_id)
                embed = msg.embeds[0]
                for i, f in enumerate(embed.fields):
                    if "Entries" in f.name:
                        embed.set_field_at(i, name="👥 Entries", value=str(len(gw["entries"])), inline=True)
                        break
                await msg.edit(embed=embed)
            except:
                pass

async def end_giveaway(msg_id: int, claim_hours: int = 6):
    gw = active_giveaways.get(msg_id)
    if not gw:
        return
    ch = bot.get_channel(gw["channel_id"])
    if not ch:
        return

    if not gw["entries"]:
        await ch.send("😔 The giveaway ended with no participants. No winner.")
        active_giveaways.pop(msg_id, None)
        return

    winner_id = random.choice(gw["entries"])
    gw["winner_id"] = winner_id
    claim_deadline = datetime.utcnow() + timedelta(hours=claim_hours)
    gw["claim_deadline"] = str(claim_deadline)
    gw["claimed"] = False

    winner = ch.guild.get_member(winner_id)
    winner_name = winner.mention if winner else f"<@{winner_id}>"

    embed = discord.Embed(
        title=f"🎉 Giveaway Ended — {gw['prize']}",
        description=(
            f"🏆 Winner: {winner_name}\n\n"
            f"Click **Claim Prize** below within **{claim_hours}h** or a new winner will be drawn!"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Claim deadline: {claim_deadline.strftime('%Y-%m-%d %H:%M')} UTC")

    claim_view = GiveawayClaimView(msg_id)
    await ch.send(content=winner_name, embed=embed, view=claim_view)

    # Schedule re-roll if not claimed
    await asyncio.sleep(claim_hours * 3600)
    gw = active_giveaways.get(msg_id)
    if gw and not gw.get("claimed", False):
        # Remove old winner, re-roll
        remaining = [uid for uid in gw["entries"] if uid != winner_id]
        if remaining:
            gw["entries"] = remaining
            await ch.send(f"⏰ {winner_name} did not claim the prize in time. Re-rolling...")
            await end_giveaway(msg_id, claim_hours)
        else:
            await ch.send("😔 No remaining participants to re-roll. Giveaway cancelled.")
            active_giveaways.pop(msg_id, None)

@bot.command(name="giveaway")
@commands.has_permissions(administrator=True)
async def giveaway_cmd(ctx, duration: str = None, claim_hours: int = 6, *, prize: str = None):
    """
    Start a giveaway.
    Usage: !giveaway <duration> [claim_hours] <prize>
    Example: !giveaway 1h 6 Discord Nitro 1 Month
    Duration: 30m / 1h / 2d
    Claim hours: how long winner has to claim (default 6h)
    """
    if not duration or not prize:
        await ctx.send(
            "❌ Usage: `!giveaway <duration> [claim_hours] <prize>`\n"
            "Example: `!giveaway 1h 6 Discord Nitro 1 Month`",
            delete_after=10
        )
        return

    seconds = parse_duration(duration)
    if seconds == 0:
        await ctx.send("❌ Invalid duration. Use format like `30m`, `1h`, `2d`.", delete_after=5)
        return

    end_time = datetime.utcnow() + timedelta(seconds=seconds)

    embed = discord.Embed(
        title=f"🎉 GIVEAWAY — {prize}",
        description=(
            f"Click **Enter Giveaway** below to participate!\n\n"
            f"⏰ Ends: <t:{int(end_time.timestamp())}:R>\n"
            f"After winning you have **{claim_hours}h** to claim your prize."
        ),
        color=discord.Color.gold()
    )
    embed.add_field(name="🎁 Prize",    value=prize,  inline=True)
    embed.add_field(name="⏱️ Duration", value=duration, inline=True)
    embed.add_field(name="👥 Entries",  value="0",    inline=True)
    embed.set_footer(text=f"Hosted by {ctx.author.display_name}")

    msg = await ctx.send(embed=embed, view=GiveawayJoinView(0))  # placeholder id

    # Now we have the real message ID
    join_view = GiveawayJoinView(msg.id)
    await msg.edit(view=join_view)

    active_giveaways[msg.id] = {
        "prize":        prize,
        "channel_id":  ctx.channel.id,
        "end_time":    str(end_time),
        "entries":     [],
        "winner_id":   None,
        "claim_deadline": None,
        "prize_code":  None,
        "claimed":     False,
    }

    await ctx.message.delete()

    # Wait for giveaway to end
    await asyncio.sleep(seconds)
    await end_giveaway(msg.id, claim_hours)

@bot.command(name="giveaway_setcode")
@commands.has_permissions(administrator=True)
async def giveaway_setcode(ctx, msg_id: str, *, code: str):
    """
    Set the prize code for a giveaway after it ends.
    Usage: !giveaway_setcode <message_id> <code>
    """
    msg_id = int(msg_id.strip().strip("`").strip())
    if ctx.author.id != OWNER_ID:
        await ctx.message.delete()
        await ctx.send("⛔ Access denied.", delete_after=3)
        return
    if msg_id not in active_giveaways:
        await ctx.send("❌ Giveaway not found. Make sure the message ID is correct.", delete_after=5)
        return
    active_giveaways[msg_id]["prize_code"] = code
    await ctx.message.delete()
    await ctx.send(f"✅ Prize code set for giveaway `{msg_id}`.", delete_after=5)

@bot.command(name="giveaway_reroll")
@commands.has_permissions(administrator=True)
async def giveaway_reroll(ctx, msg_id: str, claim_hours: int = 6):
    """
    Manually re-roll a giveaway.
    Usage: !giveaway_reroll <message_id> [claim_hours]
    """
    msg_id = int(msg_id.strip().strip("`").strip())
    if msg_id not in active_giveaways:
        await ctx.send("❌ Giveaway not found.", delete_after=5)
        return
    gw = active_giveaways[msg_id]
    prev_winner = gw.get("winner_id")
    remaining = [uid for uid in gw["entries"] if uid != prev_winner]
    if not remaining:
        await ctx.send("😔 No remaining participants to re-roll.", delete_after=5)
        return
    gw["entries"] = remaining
    gw["claimed"] = False
    await ctx.send("🔄 Re-rolling...", delete_after=3)
    await end_giveaway(msg_id, claim_hours)

@bot.command(name="giveaway_list")
@commands.has_permissions(administrator=True)
async def giveaway_list(ctx):
    """List all active giveaways."""
    if not active_giveaways:
        await ctx.send("📭 No active giveaways.", delete_after=5)
        return
    embed = discord.Embed(title="🎉 Active Giveaways", color=discord.Color.gold())
    for msg_id, gw in active_giveaways.items():
        embed.add_field(
            name=gw["prize"],
            value=(
                f"Entries: {len(gw['entries'])}\n"
                f"Channel: <#{gw['channel_id']}>\n"
                f"Message ID: `{msg_id}`\n"
                f"Code set: {'✅' if gw.get('prize_code') else '❌'}"
            ),
            inline=False
        )
    await ctx.send(embed=embed)

#  RELOAD / SYNC  (!reload)
# ─────────────────────────────────────────
@bot.command(name="reload")
@commands.has_permissions(administrator=True)
async def reload_commands(ctx):
    """Sync slash commands to this guild instantly. Usage: !reload"""
    msg = await ctx.send("🔄 Syncing slash commands...")
    try:
        # Sync globally first (registers all commands)
        await tree.sync()
        # Then copy + sync to THIS guild for instant visibility
        tree.copy_global_to(guild=ctx.guild)
        synced = await tree.sync(guild=ctx.guild)
        await msg.edit(content=f"✅ **{len(synced)} command(s)** synced instantly to **{ctx.guild.name}**! They should appear now after Ctrl+R.")
        print(f"[RELOAD] {len(synced)} commands synced to guild by {ctx.author}")
    except Exception as e:
        await msg.edit(content=f"❌ Sync failed: `{e}`")

# ─────────────────────────────────────────
#  ERROR HANDLER
# ─────────────────────────────────────────
@tree.error
async def on_app_command_error(i: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await i.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.CommandOnCooldown):
        await i.response.send_message(f"⏳ Cooldown! Try again in {error.retry_after:.1f}s.", ephemeral=True)
    else:
        await i.response.send_message(f"❌ Error: `{error}`", ephemeral=True)

# ══════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════
bot.run(TOKEN)
