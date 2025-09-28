import re
import os
import random
import aiohttp
from pathlib import Path
from math import ceil
from astrbot.api.event import filter, AstrMessageEvent
import astrbot.api.message_components as Comp
from astrbot.api.message_components import Node, Plain, Image as CompImage
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot import logger

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
}
BASE_URLS = [
    "https://api.asmr.one",
    "https://api.asmr-100.com",
    "https://api.asmr-200.com",
    "https://api.asmr-300.com"
]
@register(
    "astrbot_plugin_asmr",
    "CCYellowStar2",
    "ASMR音声搜索与播放",
    "1.0",
    "https://github.com/CCYellowStar2/astrbot_plugin_asmr"
)
class AsmrPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig=None):
        super().__init__(context)
        # 初始化配置项
        self.timeout = 30
        self.base_urls = BASE_URLS
        self.current_api_index = 0  # 当前使用的API索引
        self.plugin_dir = Path(__file__).parent
        self.template_path = self.plugin_dir / "md.html"

    async def rotate_api(self):
        """切换到下一个API端点"""
        self.current_api_index = (self.current_api_index + 1) % len(self.base_urls)
        logger.info(f"切换到API: {self.base_urls[self.current_api_index]}")

    def get_current_api(self):
        """获取当前API端点"""
        return self.base_urls[self.current_api_index]

    async def fetch_with_retry(self, url_path: str, params=None, max_retries=4):
        """带重试机制的API请求"""
        errors = []
        async with aiohttp.ClientSession(headers=headers) as session: # 在循环外创建会SH会话
            for attempt in range(max_retries):
                current_api = self.get_current_api()
                url = f"{current_api}{url_path}"
                try:
                    # 复用 session
                    async with session.get(url, params=params, timeout=10) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            errors.append(f"API {current_api} 返回状态码: {response.status}")
                            await self.rotate_api()
                except Exception as e:
                    errors.append(f"API {current_api} 请求失败: {str(e)}")
                    await self.rotate_api()
        
        error_msg = "所有API请求均失败:\n" + "\n".join(errors)
        logger.error(error_msg)
        return None

    
    @filter.command("搜音声")
    async def search_asmr(self, event: AstrMessageEvent):
        """搜索音声"""
        args = event.message_str.replace("搜音声", "").split()
        if not args:
            yield event.plain_result("请输入搜索关键词(用'/'分割不同tag)和搜索页数(可选)！比如'搜音声 伪娘/催眠 1'")
            return

        # 解析参数
        y = 1
        keyword = ""
        if len(args) == 1:
            keyword = args[0].replace("/", "%20")
        elif len(args) == 2:
            keyword = args[0].replace("/", "%20")
            try:
                y = int(args[1])
            except ValueError:
                yield event.plain_result("页数必须是数字")
                return
        else:
            yield event.plain_result("请正确输入搜索关键词(用'/'分割不同tag)和搜索页数(可选)！比如'搜音声 伪娘/催眠 1'")
            return

        yield event.plain_result(f"正在搜索音声{keyword}，第{y}页！")

        try:
            r = await self.fetch_with_retry(
                f"/api/search/{keyword}",
                params={
                    "order": "dl_count",
                    "sort": "desc",
                    "page": y,
                    "subtitle": 0,
                    "includeTranslationWorks": "true"
                }
            )
            
            if r is None:
                yield event.plain_result("搜索音声失败，请稍后再试")
                return
            
            if len(r["works"]) == 0:
                if r["pagination"]["totalCount"] == 0:
                    yield event.plain_result("搜索结果为空")
                    return
                elif r["pagination"]["currentPage"] > 1:
                    count = int(r["pagination"]["totalCount"])
                    max_pages = ceil(count / 20)
                    yield event.plain_result(f"此搜索结果最多{max_pages}页")
                    return
            
            # 处理搜索结果
            title, ars, imgs, rid = [], [], [], []
            for result2 in r["works"]:
                title.append(result2["title"])
                ars.append(result2["name"])
                imgs.append(result2["mainCoverUrl"])
                ids = str(result2["id"])
                if len(ids) == 7 or len(ids) == 5:
                    ids = "RJ0" + ids
                else:
                    ids = "RJ" + ids
                rid.append(ids)
            
            # 生成Markdown格式结果
            msg2 = f'### <div align="center">搜索结果</div>\n' \
                    f'| 封面 | 序号 | RJ号 |\n' \
                    '| --- | --- | --- |\n'
            
            msg = ""
            for i in range(len(title)):
                msg += str(i + 1) + ". 【" + rid[i] + "】 " + title[i] + "\n"
                msg2 += f'|<img width="250" src="{imgs[i]}"/> | {str(i+1)}. |【{rid[i]}】|\n'
            
            msg += "请发送听音声+RJ号+节目编号（可选）来获取要听的资源"
            chain = []
            # 渲染Markdown为图片
            template_data = {
                "text": msg2
            }
            with open(self.template_path, 'r', encoding='utf-8') as f:
                meme_help_tmpl = f.read()
            url = await self.html_render(meme_help_tmpl, template_data)
            chain.append(CompImage.fromURL(url))
            chain.append(Plain(msg))
            node = Node(
                uin=3974507586,
                name="玖玖瑠",
                content=chain
            )
            yield event.chain_result([node])
            
        except Exception as e:
            logger.error(f"搜索音声失败: {str(e)}")
            yield event.plain_result("搜索音声失败，请稍后再试")

    @filter.command("听音声")
    async def play_asmr(self, event: AstrMessageEvent):
        """播放音声"""
        args = event.message_str.replace("听音声", "").split()
        substrings = ["RJ", "rj", "Rj", "rJ"]
        
        if not args:
            yield event.plain_result("请输入RJ号！")
            return
        
        rid = args[0]   

        for sub in substrings:
            if sub in args[0]:
                rid = args[0].replace(sub, "")
                break
        
        try:
            y = int(rid)
        except ValueError:
            yield event.plain_result("请输入正确的RJ号！")
            return
        selected_index = int(args[1]) - 1 if len(args) > 1 and args[1].isdigit() else None
        
        yield event.plain_result(f"正在查询音声信息！")
        
        try:
                # 获取音声信息
                r = await self.fetch_with_retry(f"/api/workInfo/{rid}")
                
                if r is None or "title" not in r:
                    yield event.plain_result("没有此音声信息或还没有资源")
                    return
                if selected_index:
                    msg1,url,state=await self.get_asmr(event=event,rid=rid,r=r,selected_index=selected_index)
                else:
                    msg1,url,state=await self.get_asmr(event=event,rid=rid,r=r)
                if state == None:
                    return
                yield event.image_result(url)
                yield event.plain_result(msg1)
                
                id = event.get_sender_id()
                @session_waiter(timeout=self.timeout, record_history_chains=False)
                async def track_waiter(controller: SessionController, ev: AstrMessageEvent):
                    if ev.get_sender_id() != id:
                        return
                    reply = ev.message_str.strip()
                    if not reply.isdigit():
                        await event.send(event.plain_result("请发送正确的数字~"))
                        return
                    
                    index = int(reply) - 1
                    if index < 0 or index >= len(state["keywords"]):
                        await event.send(event.plain_result("序号超出范围，请重新输入"))
                        return
                    
                    await self._play_track(ev, index, state["keywords"], state["urls"], 
                                          state["name"], state["ar"], state["iurl"], state["rid"])
                    controller.stop()
                
                try:
                    await track_waiter(event)
                except TimeoutError:
                    yield event.plain_result("选择超时！")
        except Exception as e:
            logger.error(f"播放音声失败: {str(e)}")
            yield event.plain_result("播放音声失败，请稍后再试")

    @filter.command("随机音声")
    async def play_Random_asmr(self, event: AstrMessageEvent):
        """播放随机音声"""        
        yield event.plain_result(f"正在随机抽取音声！")
        
        try:
                # 获取音声信息
                r = (await self.fetch_with_retry(f"/api/works?order=betterRandom"))["works"][0]
                
                if r is None or "title" not in r:
                    yield event.plain_result("没有此音声信息或还没有资源")
                    return
                rid = str(r["id"])
                if len(rid) == 7 or len(rid) == 5:
                    rid = "0" + rid
                yield event.plain_result("抽取成功！RJ号："+rid)
                msg1,url,state=await self.get_asmr(event=event,rid=rid,r=r)
                if state == None:
                    return
                yield event.image_result(url)
                yield event.plain_result(msg1)
                
                id = event.get_sender_id()
                @session_waiter(timeout=self.timeout, record_history_chains=False)
                async def track_waiter(controller: SessionController, ev: AstrMessageEvent):
                    if ev.get_sender_id() != id:
                        return
                    reply = ev.message_str.strip()
                    if not reply.isdigit():
                        await event.send(event.plain_result("请发送正确的数字~"))
                        return
                    
                    index = int(reply) - 1
                    if index < 0 or index >= len(state["keywords"]):
                        await event.send(event.plain_result("序号超出范围，请重新输入"))
                        return
                    
                    await self._play_track(ev, index, state["keywords"], state["urls"], 
                                          state["name"], state["ar"], state["iurl"], state["rid"])
                    controller.stop()
                
                try:
                    await track_waiter(event)
                except TimeoutError:
                    yield event.plain_result("选择超时！")
        except Exception as e:
            logger.error(f"播放音声失败: {str(e)}")
            yield event.plain_result("播放音声失败，请稍后再试")

    async def get_asmr(self, event: AstrMessageEvent, rid: str, r, selected_index: int = 0):        
        name = r["title"]
        ar = r["name"]
        img = r["mainCoverUrl"]
        
        # 获取音轨信息
        result = await self.fetch_with_retry(f"/api/tracks/{rid}")
        
        if result is None:
            await event.send(event.plain_result("获取音轨信息失败"))
            return None,None,None
        
        keywords, urls = [], []
        
        async def process_item(item):
            if item["type"] == "audio":
                keywords.append(item["title"])
                urls.append(item["mediaDownloadUrl"])
            elif item["type"] == "folder":
                for child in item["children"]:
                    await process_item(child)
        
        for result2 in result:
            await process_item(result2)
        
        if not keywords:
            await event.send(event.plain_result("此音声没有可播放的音轨"))
            return None,None,None
        
        # 如果提供了索引，直接播放
        if selected_index and selected_index != 0:
            await self._play_track(event, selected_index, keywords, urls, name, ar, img, rid)
            return None,None,None
        
        # 否则显示选择界面
        msg = f'### <div align="center">选择编号</div>\n' \
            f'|<img width="250" src="{img}"/> |{name}  社团名：{ar}|\n' \
            '| :---: | --- |\n'
        
        for i in range(len(keywords)):
            msg += f'|{str(i+1)}. | {keywords[i]}|\n'
        
        msg1 = "请发送序号来获取要听的资源"
            
        template_data = {
            "text": msg
        }
        with open(self.template_path, 'r', encoding='utf-8') as f:
            meme_help_tmpl = f.read()
        url = await self.html_render(meme_help_tmpl, template_data)

        state = {
            "keywords": keywords,
            "urls": urls,
            "ar": ar,
            "url": f"https://asmr.one/work/RJ{rid}",
            "iurl": img,
            "name": name,
            "rid": rid
        }
        return msg1,url,state

    async def _play_track(self, event: AstrMessageEvent, index: int, keywords: list, 
                         urls: list, name: str, ar: str, img: str, rid: str):
        """播放指定音轨"""
        # 修正索引范围
        if index < 0:
            index = 0
        elif index >= len(urls):
            index = len(urls) - 1
        
        track_name = keywords[index]
        audio_url = urls[index]
        asmr_url = f"https://asmr.one/work/RJ{rid}"
        
        # 平台适配
        platform_name = event.get_platform_name()
        
        # QQ平台发送自定义音乐卡片
        if platform_name == "aiocqhttp":
            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            is_private = event.is_private_chat()
    
            headers2 = {
                "Content-Type":"application/json"
            }
            data={
                "url": audio_url,
                "song": track_name,
                "singer": ar,
                "cover": img,
                "jump": asmr_url,
                "format": "163",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post("https://oiapi.net/API/QQMusicJSONArk", json=data, headers=headers2, timeout=10) as response:
                    if response.status == 200:
                        js = (await response.json()).get("message")        
                        payloads = {
                            "message": [
                                {
                                    "type": "json",
                                    "data": {
                                        "data": js,
                                    },
                                }
                            ],
                        }
                        
                        if is_private:
                            payloads["user_id"] = event.get_sender_id()
                            await client.api.call_action("send_private_msg", **payloads)
                        else:
                            payloads["group_id"] = event.get_group_id()
                            await client.api.call_action("send_group_msg", **payloads)
                    else:
                        audio_info = (
                            f"🎧 {track_name}\n"
                            f"📻 {name} - {ar}\n"
                            f"🔗 音频链接: {audio_url}\n"
                            f"🌐 作品页面: {asmr_url}"
                        )
                        await event.send(event.plain_result(audio_info))
        
        # 其他平台发送音频链接
        else:
            audio_info = (
                f"🎧 {track_name}\n"
                f"📻 {name} - {ar}\n"
                f"🔗 音频链接: {audio_url}\n"
                f"🌐 作品页面: {asmr_url}"
            )
            await event.send(event.plain_result(audio_info))
