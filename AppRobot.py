#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import random
import subprocess
import sys
import time
import uiautomator2 as u2


class AdbCommand:

    def __init__(self, *args):
        self.devices = [
            {"device": device, "u": u2.connect(device)}
            for device in (list(args) if len(args) > 0 else self.getDevics())
        ]
        # print(self.devices)

    def adb_shell(self, cmd):
        result = subprocess.getstatusoutput(cmd)
        if result[0] == 0:
            return result
        else:
            print("执行命令失败！！")
            sys.exit(0)

    async def adb_shell_async(self, cmd):
        """异步执行 ADB 命令"""
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            return process.returncode, stdout.decode().strip()
        else:
            print(f"执行命令失败: {cmd}")
            print(f"错误: {stderr.decode().strip()}")
            sys.exit(0)

    def getDevics(self):
        result = self.adb_shell("adb devices")
        device_list = result[1].splitlines()[1:]
        print(f"发现 {len(device_list)} 个设备: {device_list}")
        return [device.split("\t")[0] for device in device_list if "device" in device]

    def getDeviceSize(self):
        for deviced in self.devices:
            device = deviced["device"]
            result = self.adb_shell(f"adb -s {device} shell wm size")
            sizes = result[1].splitlines()
            for s in sizes:
                deviced["size"] = s.split(":")[1].strip()

    def dump_hierarchy(self):
        # 获取当前界面的控件树XML (dump hierarchy)
        xml_root = self.devices[0].get("u").dump_hierarchy()
        with open("hierarchy.xml", "w", encoding="utf-8") as f:
            f.write(xml_root)

    def back_to_main(self, u, target_id="com.ss.android.ugc.aweme:id/d5d", max_try=5):
        """返回主界面"""
        for i in range(max_try):
            # 等待元素出现，设置较短超时（例如2秒）
            if u(resourceId=target_id).wait(timeout=2.0):
                print("目标元素已出现")
                break
            else:
                print(f"等待超时，按返回键 (第{i+1}次)")
                u.press("back")
        else:
            print("达到最大返回次数，仍未找到目标元素")

        # # 检查包含该文本的元素是否存在（可根据需要改用 text、textContains 等）
        # if d(textContains=target_text).exists:
        #     print(f"目标文本 '{target_text}' 已出现")
        #     break
        # else:
        #     print(f"第 {attempt+1} 次未找到，按返回键")
        #     d.press("back")
        #     time.sleep(1)  # 等待页面切换动画
        #     attempt += 1

    def dy_like(self, u):
        """抖音点赞"""
        # 抖音点赞id
        btn = u(resourceId="com.ss.android.ugc.aweme:id/frt")
        btn.wait(timeout=5.0)  # 等待最多5秒
        # 获取当前控件的 content-desc 属性
        desc = btn.info.get("contentDescription", "")
        if "未点赞" in desc:
            btn.click()
            time.sleep(0.5)

    def dy_collect(self, u):
        """抖音收藏"""
        # 抖音收藏
        btn = u(resourceId="com.ss.android.ugc.aweme:id/dt6")
        btn.wait(timeout=5.0)  # 等待最多5秒
        # 获取当前控件的 content-desc 属性
        desc = btn.info.get("contentDescription", "")
        # print(f"当前 content-desc: {desc}")
        if "未选中" in desc:
            # self.adb_shell(f'adb -s {device_id} shell input tap 1108 1907')
            btn.click()
            time.sleep(1)
            # print("执行点击")
        # elif '已选中' in desc:
        #     pass
        # print("已选中状态，不点击")

    def dy_comment(self, u):
        """抖音评论"""
        # 评论
        btn = u(resourceId="com.ss.android.ugc.aweme:id/d5d")
        btn.wait(timeout=5.0)  # 等待最多5秒
        btn.click()
        time.sleep(1)

        try:
            # 点击表情
            btn = u(resourceId="com.ss.android.ugc.aweme:id/l_o")
            btn.wait(timeout=5.0)  # 等待最多5秒
            btn.click()
        except Exception as e:
            print(f"点击表情异常：{e}")

        try:
            time.sleep(0.5)
            btn = u.xpath('(//*[@resource-id="com.ss.android.ugc.aweme:id/ysh"])[2]')
            btn.wait(timeout=2.0)  # 等待最多5秒
            btn.click()
            time.sleep(0.5)

            btn = u.xpath(
                f'//*[@content-desc="自定义表情{random.randint(1, 2)}, 按钮"]'
            )
            btn.wait(timeout=5.0)  # 等待最多5秒
            btn.click()
            time.sleep(0.5)
            # 发送评论
            btn = u(resourceId="com.ss.android.ugc.aweme:id/d2h")
            btn.wait(timeout=5.0)  # 等待最多5秒
            btn.click()
        except Exception as e:
            print(f"评论异常：{e}")
        finally:
            # 关闭评论
            try:
                time.sleep(1)
                btn = u(resourceId="com.ss.android.ugc.aweme:id/back_btn")
                btn.wait(timeout=2.0)  # 等待最多5秒
                btn.click()
                self.back_to_main(u=u)
            except Exception as e:
                print(f"关闭评论异常：{e}")

    def dy_recommend(self, u):
        """抖音推荐"""
        # 抖音推荐
        # 分享
        btn = u(resourceId="com.ss.android.ugc.aweme:id/w7n")
        btn.wait(timeout=5.0)  # 等待最多5秒
        btn.click()
        time.sleep(2)
        # 推荐图标
        # com.ss.android.ugc.aweme:id/w1z
        # 推荐文本
        # com.ss.android.ugc.aweme:id/w33
        all_btns = u.xpath('//*[@resource-id="com.ss.android.ugc.aweme:id/w33"]').all()
        for index, btn in enumerate(all_btns):
            text = btn.info.get("text", "")
            if "推荐" in text:
                if text == "推荐":
                    btn.click()
                    time.sleep(1)
                    break
                else:
                    print(f"推荐文本: {text}")
                    # 返回
                    u.press("back")
                    time.sleep(1)

    def dy_swip(self):
        # 获取设备宽高
        if len(self.devices) > 0:
            self.getDeviceSize()
        else:
            print("没有设备！")
            sys.exit(0)

        for i in range(1000):
            for device in self.devices:
                device_id = device.get("device")
                u = device.get("u")
                x = float(device.get("size").split("x")[0]) / 2
                y1 = float(device.get("size").split("x")[1]) / 6 * 5
                y2 = float(device.get("size").split("x")[1]) / 3

                # 抖音点赞
                # self.dy_like(u)

                # 抖音收藏
                # self.dy_collect(u)

                # 抖音评论
                # self.dy_comment(u)

                # 抖音推荐
                # self.dy_recommend(u)

                # 滑动下一个视频
                time.sleep(1)

                # 获取评论数量
                btn = u(resourceId="com.ss.android.ugc.aweme:id/d5d")
                btn.wait(timeout=5.0)  # 等待最多5秒
                desc_com = btn.info.get("contentDescription", "")

                # 获取点赞数量
                btn = u(resourceId="com.ss.android.ugc.aweme:id/frt")
                btn.wait(timeout=5.0)  # 等待最多5秒
                # 获取当前控件的 content-desc 属性
                desc_like = btn.info.get("contentDescription", "")

                self.adb_shell(
                    f"adb -s {device_id} shell input swipe {x} {y1} {x} {y2}"
                )
                time.sleep(random.randint(1, 3))

                btn = u(resourceId="com.ss.android.ugc.aweme:id/d5d")
                btn.wait(timeout=5.0)  # 等待最多5秒
                desc_com2 = btn.info.get("contentDescription", "")

                btn = u(resourceId="com.ss.android.ugc.aweme:id/frt")
                btn.wait(timeout=5.0)  # 等待最多5秒
                # 获取当前控件的 content-desc 属性
                desc_like2 = btn.info.get("contentDescription", "")

                if desc_com == desc_com2 and desc_like == desc_like2:
                    print(f"已无更多视频，评论数：{desc_com}，点赞数：{desc_like}")
                    exit(0)

    def ks_swip(self):
        # 获取设备宽高
        if len(self.devices) > 0:
            self.getDeviceSize()
        else:
            print("没有设备！")
            sys.exit(0)

        for i in range(1000):
            for j in range(9):
                for device in self.devices:
                    device_id = device.get("device")
                    u = device.get("u")
                    x = float(device.get("size").split("x")[0]) / 2
                    y1 = float(device.get("size").split("x")[1]) / 6 * 5
                    y2 = float(device.get("size").split("x")[1]) / 3

                    # 滑动下一个视频
                    # time.sleep(1)
                    # i 为偶数时，从下往上滑动，为奇数时，从上往下滑动
                    self.adb_shell(
                        f"adb -s {device_id} shell input swipe {x} {y1 if i % 2 == 0 else y2} {x} {y2 if i % 2 == 0 else y1}"
                    )
                    time.sleep(random.randint(1, 2))

    def add_video_to_favorites(self):
        # 添加视频进收藏夹
        u = self.devices[0].get("u")

        for i in range(5):
            time.sleep(2)
            btn = u(text="管理")
            btn.wait(timeout=5.0)
            btn.click()

            btn = u(text="添加视频")
            btn.wait(timeout=5.0)
            btn.click()

            time.sleep(5)

            # 获取所有匹配的控件对象列表
            all_btns = u.xpath(
                '//*[@resource-id="com.ss.android.ugc.aweme:id/ii_"]'
            ).all()
            # print(all_btns)
            if len(all_btns) <= 2:
                time.sleep(15)
                all_btns = u.xpath(
                    '//*[@resource-id="com.ss.android.ugc.aweme:id/ii_"]'
                ).all()
                if len(all_btns) <= 0:
                    break

            for btn in all_btns:
                btn.click()

            time.sleep(2)
            btn = u(text="添加")
            btn.wait(timeout=5.0)
            btn.click()

    async def swipe_device_loop(self, device, rng, max_swipes=1000, max_per_round=9):
        """单个设备的独立滑动循环"""
        device_id = device.get("device")
        u = device.get("u")
        x = float(device.get("size").split("x")[0]) / 2
        y1 = float(device.get("size").split("x")[1]) / 6 * 5
        y2 = float(device.get("size").split("x")[1]) / 3

        for i in range(max_swipes):
            for _ in range(max_per_round):
                # 执行滑动
                await self.adb_shell_async(
                    f"adb -s {device_id} shell input swipe {x} {y1 if i % 2 == 0 else y2} {x} {y2 if i % 2 == 0 else y1}"
                )
                # 随机等待，每个设备独立
                rand_sleep = rng.randint(10, 30) / 10
                # print(f"设备 {device_id} 随机等待 {rand_sleep} 秒")
                await asyncio.sleep(rand_sleep)

    async def ks_swip_async(self):
        """异步版本 ks_swip - 每个设备独立运行"""
        if len(self.devices) > 0:
            self.getDeviceSize()
        else:
            print("没有设备！")
            sys.exit(0)

        # 为每个设备创建独立的随机数生成器
        rngs = [random.Random() for _ in self.devices]

        # 为每个设备创建独立的异步任务，不等待彼此
        tasks = [
            self.swipe_device_loop(device, rng)
            for device, rng in zip(self.devices, rngs)
        ]

        # 并发运行所有设备的循环
        await asyncio.gather(*tasks)


if __name__ == "__main__":

    try:
        adb = AdbCommand()
        # adb.dy_swip()
        # adb.ks_swip()
        # adb.dump_hierarchy()
        # adb.add_video_to_favorites()
        asyncio.run(adb.ks_swip_async())
    except KeyboardInterrupt:
        print(f"用户中断程序")
        sys.exit(0)
    except TimeoutError as e:
        print(f"超时异常：{e}")
        sys.exit(0)
    except Exception as e:
        # ctrl+c 退出程序
        print(f"退出程序")
        sys.exit(0)
