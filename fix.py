import matplotlib.pyplot as plt

# 设置中文字体（确保在不同环境下能正常显示）
plt.rcParams['font.sans-serif'] = ['SimHei'] 
plt.rcParams['axes.unicode_minus'] = False

# 数据准备
labels = ['2分 (优秀)', '1分 (合格)', '0分 (失误)']
sizes = [34, 5, 1]
colors = ['#4CAF50', '#FFC107', '#F44336'] # 绿色、黄色、红色
explode = (0.1, 0, 0)  # 将优秀部分稍微分离出来突出显示

# 绘制饼图
plt.figure(figsize=(8, 6))
plt.pie(sizes, explode=explode, labels=labels, colors=colors,
        autopct='%1.1f%%', shadow=True, startangle=140)

plt.title('国际杰青计划 40道题测评得分分布', fontsize=15)
plt.axis('equal')  # 保证饼图是正圆

plt.show()