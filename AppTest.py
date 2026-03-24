# coding=utf-8
"""
 @Time : 2022/11/3 13:30 
 @Author : wwf
"""
import os
import random
import subprocess
import sys
import time
import uiautomator2 as u2

# 方法一：os.system()

# 返回值：返回对应状态码，且状态码只会有0(成功)、1、2。

# 其它说明：os.system()的返回值并不是执行程序的返回结果。而是一个16位的数，它的高位才是返回码。也就是说os.system()执行返回256即 0×0100，返回码应该是其高位0×01即1。所以要获取它的状态码的话，需要通过>>8移位获取。def adb_shell(cmd):

# exit_code = os.system(cmd)
#
# return exit_code>>8

# # os.system(cmd)命令会直接把结果输出，所以在不对状态码进行分析处理的情况下，一般直接调用即可 # os.system(cmd)

# # 方法二：os.popen()

# # 返回值：返回脚本命令输出的内容

# # 其它说明：os.popen()可以实现一个“管道”，从这个命令获取的值可以继续被调用。而os.system不同，它只是调用，调用完后自身退出，执行成功直接返回个0。

def adb_shell2(cmd):
    result = os.popen(cmd).read()

    return result


# 方法三：subprocess.Popen()

# 返回值：Popen类的构造函数，返回结果为subprocess.Popen对象，脚本命令的执行结果可以通过stdout.read()获取。
def adb_shell3(cmd):
    # 执行cmd命令，如果成功，返回(0, 'xxx')；如果失败，返回(1, 'xxx')

    res = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)  # 使用管道

    result = res.stdout.read()  # 获取输出结果

    res.wait()  # 等待命令执行完成

    res.stdout.close()  # 关闭标准输出

    return result


# # 方法四：subprocess.getstatusoutput()

# # 返回值：返回是一个元组，如果成功，返回(0, 'xxx')；如果失败，返回(1, 'xxx')

def adb_shell4(cmd):
    result = subprocess.getstatusoutput(cmd)

    return result


# cmd = 'adb shell dumpsys activity | grep "Run #"'


class AdbCommand():

    def __init__(self, *args):
        self.devices = [{'device': device,"u":u2.connect(device)} for device in (list(args) if len(args) > 0 else self.getDevics())]
        # print(self.devices)

    def adb_shell(self, cmd):
        result = subprocess.getstatusoutput(cmd)
        if result[0] == 0:
            return result
        else:
            print('执行命令失败！！')
            sys.exit(0)

    def getDevics(self):
        result = self.adb_shell('adb devices')
        device_list = result[1].splitlines()[1:]
        return [device.split('\t')[0] for device in device_list if 'device' in device]

    def getDeviceSize(self):
        for deviced in self.devices:
            device = deviced['device']
            result = self.adb_shell(f'adb -s {device} shell wm size')
            sizes = result[1].splitlines()
            for s in sizes:
                deviced['size'] = s.split(':')[1].strip()

    def swip(self):
        # 获取设备宽高
        if len(self.devices) > 0:
            self.getDeviceSize()
        else:
            print('没有设备！')
            sys.exit(0)

        for i in range(1000):
            for device in self.devices:
                device_id = device.get("device")
                x = float(device.get("size").split("x")[0]) / 2
                y1 = float(device.get("size").split("x")[1]) / 6 * 5
                y2 = float(device.get("size").split("x")[1]) / 3
                

                # 抖音点赞id
                btn = device.get("u")(resourceId="com.ss.android.ugc.aweme:id/frt")
                btn.wait(timeout=5.0)  # 等待最多5秒
                # 获取当前控件的 content-desc 属性
                desc = btn.info.get('contentDescription', '')
                if '未点赞' in desc:
                    btn.click()
                    time.sleep(0.5)
                else:
                    print("未知状态，请检查")



                # 抖音收藏id
                btn = device.get("u")(resourceId="com.ss.android.ugc.aweme:id/dt6")
                btn.wait(timeout=5.0)  # 等待最多5秒
                # 获取当前控件的 content-desc 属性
                desc = btn.info.get('contentDescription', '')
                # print(f"当前 content-desc: {desc}")
                if '未选中' in desc:
                    # self.adb_shell(f'adb -s {device_id} shell input tap 1108 1907')
                    btn.click()
                    time.sleep(1)
                    # print("执行点击")
                elif '已选中' in desc:
                    pass
                    # print("已选中状态，不点击")
                else:
                    print("未知状态，请检查")
                
                self.adb_shell(f'adb -s {device_id} shell input swipe {x} {y1} {x} {y2}')
                time.sleep(random.randint(1, 3))
    
    def add_video_to_favorites(self):
        # 添加视频进收藏夹
        u = self.devices[0].get("u")

        for i in range(10):
            time.sleep(2)
            btn = u(text="管理")
            btn.wait(timeout=5.0)
            btn.click()

            btn = u(text="添加视频")
            btn.wait(timeout=5.0)
            btn.click()

            time.sleep(5)
            
            # 获取当前界面的控件树XML (dump hierarchy)
            # xml_root = self.devices[0].get("u").dump_hierarchy()    
            # with open('hierarchy.xml', 'w', encoding='utf-8') as f:
            #     f.write(xml_root)


            # 获取所有匹配的控件对象列表
            all_btns = u.xpath('//*[@resource-id="com.ss.android.ugc.aweme:id/ii_"]').all()
            # print(all_btns)
            if len(all_btns) <= 2:
                time.sleep(5)
                all_btns = u.xpath('//*[@resource-id="com.ss.android.ugc.aweme:id/ii_"]').all()
                if len(all_btns) <= 0:
                    break

            for btn in all_btns:
                btn.click()

            time.sleep(2)
            btn = u(text="添加")
            btn.wait(timeout=5.0)
            btn.click()

if __name__ == '__main__':
    
    try:
        adb = AdbCommand()
        adb.swip()
        # adb.add_video_to_favorites()
    except:
        print('结束程序！')
        sys.exit(0)
