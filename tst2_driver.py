from neo4j import GraphDatabase
import logging
from neo4j.exceptions import ServiceUnavailable
from flask import Flask, render_template, request, json, jsonify
from fuzzywuzzy import process
from rtasr import dictation
import global_var

class App:

    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        # Don't forget to close the driver connection when you are finished with it
        self.driver.close()

    def create_friendship(self, person1_name, person2_name):
        with self.driver.session() as session:
            # Write transactions allow the driver to handle retries and transient errors
            result = session.write_transaction(
                self._create_and_return_friendship, person1_name, person2_name)
            for row in result:
                print("Created friendship between: {p1}, {p2}".format(p1=row['p1'], p2=row['p2']))

    @staticmethod
    def _create_and_return_friendship(tx, person1_name, person2_name):
        # To learn more about the Cypher syntax, see https://neo4j.com/docs/cypher-manual/current/
        # The Reference Card is also a good resource for keywords https://neo4j.com/docs/cypher-refcard/current/
        query = (
            "CREATE (p1:Person { name: $person1_name }) "
            "CREATE (p2:Person { name: $person2_name }) "
            "CREATE (p1)-[:KNOWS]->(p2) "
            "RETURN p1, p2"
        )
        result = tx.run(query, person1_name=person1_name, person2_name=person2_name)
        try:
            return [{"p1": row["p1"]["name"], "p2": row["p2"]["name"]}
                    for row in result]
        # Capture any errors along with the query and data for traceability
        except ServiceUnavailable as exception:
            logging.error("{query} raised an error: \n {exception}".format(
                query=query, exception=exception))
            raise

    def find_person(self, person_name, nodeType):
        with self.driver.session() as session:
            result = session.read_transaction(self._find_and_return_person, person_name, nodeType)
            return result
            # for row in result:
            #    print("Found person: {row}".format(row=row))

    @staticmethod
    def _find_and_return_person(tx, person_name, nodeType):
        result = []
        if nodeType == "function":  # 查找的是一个function节点，共有两种边的链接情况，have_technology_of出去，have_function_of进入

            query = (
                "MATCH (p:Function)-[:have_technology_of]->(a:Technology)"
                                                             "WHERE p.function = $person_name "
                                                             "RETURN a.name AS l"  # .roles AS roles
                # "RETURN p.name AS name"
            )
            result_temp = tx.run(query, person_name=person_name)
            result.append([row["l"] for row in result_temp])  # have_technology_of往外连

            query = (
                "MATCH (p:Function)<-[:have_function_of]-(a:Sustainable)"
                "WHERE p.function = $person_name "
                "RETURN a.goal AS l"  # .roles AS roles
                # "RETURN p.name AS name"
            )
            result_temp = tx.run(query, person_name=person_name)
            result.append([row["l"] for row in result_temp])  # have_function_of往内连

            result.append("Function")  # 最后添加标识符，表示是Function节点

            # print(result)

        elif nodeType == "sustain":  # 查找的是一个sustainable节点，共有三种边的链接情况，分别是subclass_of往外连，subclass_of往里连，have_function_of往外连
            query = (
                "MATCH (p:Sustainable)-[:subclass_of]->(a:Sustainable)"
                "WHERE p.goal = $person_name "
                "RETURN a.goal AS l"  # .roles AS roles
            )
            result_temp = tx.run(query, person_name=person_name)
            result.append([row["l"] for row in result_temp])  # sustainable往外连

            query = (
                "MATCH (p:Sustainable)<-[:subclass_of]-(a:Sustainable)"
                "WHERE p.goal = $person_name "
                "RETURN a.goal AS l"  # .roles AS roles
            )
            result_temp = tx.run(query, person_name=person_name)
            result.append([row["l"] for row in result_temp])  # sustainable往内连

            query = (
                "MATCH (p:Sustainable)-[:have_function_of]->(a:Function)"
                "WHERE p.goal = $person_name "
                "RETURN a.function AS l"  # .roles AS roles
            )
            result_temp = tx.run(query, person_name=person_name)
            result.append([row["l"] for row in result_temp])  # sustainable连have_function_of

            result.append("Sustainable")  # 最后添加标识符，表示是Sustainable节点

        elif nodeType == "technology":  # 查找的是一个technology节点
            query = (
                "MATCH (p:Technology)<-[have_technology_of]-(a:Function)"
                                                             "WHERE p.name = $person_name "
                                                             "RETURN a.function AS l"  # .roles AS roles
                # "RETURN p.name AS name"
            )
            result_temp = tx.run(query, person_name=person_name)
            result.append([row["l"] for row in result_temp])  # have_technology_of往内连

            result.append("Technology")  # 最后添加标识符，表示是Technology节点

        # print(query)
        # query = (
        #     "MATCH (p:Sustainable)-[:" + str(relation) + "]->(a:Function)"
        #                                                  "WHERE p.goal = $person_name "
        #                                                  "RETURN a.function AS l"  # .roles AS roles
        #     # "RETURN p.name AS name"
        # )
        # result = tx.run(query, person_name=person_name)
        # print([row["l"] for row in result])
        # return [row["name"] for row in result]
        return result


def dataFormatting(linkTo, sourceName):
    nodes_trans = []
    links_trans = []
    # nodes_seen = []
    susColor = "#73AD69"
    funcColor = "#6499B0"
    techColor = "#886CC5"
    subclassColor = "#BEBEBE"
    havefuncColor = "#A490CD"
    havetechColor = "#93BCCD"
    curId = 1

    if linkTo[-1] == "Sustainable":  # 是Sustainable节点
        nodes_trans.append({"id": 0, "name": sourceName, "category": 0, "colors": susColor})  # 起点
        # nodes_seen.append(sourceName)

        for i in linkTo[0]:  # subclass_of往外连
            # if i not in nodes_seen:  # 去重
            #     nodes_seen.append(i)
            nodes_trans.append({"id": curId, "name": i, "category": 0, "colors": susColor})

            curId += 1
            links_trans.append(
                {"source": 0, "target": curId - 1, "value": "subclass_of", "lineStyle": {"color": subclassColor}})

        for i in linkTo[1]:  # subclass_of往里连
            # if i not in nodes_seen:  # 去重
            #     nodes_seen.append(i)
            nodes_trans.append({"id": curId, "name": i, "category": 0, "colors": susColor})  # 邻接点

            curId += 1
            links_trans.append(
                {"source": curId - 1, "target": 0, "value": "subclass_of", "lineStyle": {"color": subclassColor}})

        for i in linkTo[2]:  # have_function_of
            # if i not in nodes_seen:  # 去重
            #     nodes_seen.append(i)
            nodes_trans.append({"id": curId, "name": i, "category": 1, "colors": funcColor})

            curId += 1
            links_trans.append(
                {"source": 0, "target": curId - 1, "value": "have_function_of", "lineStyle": {"color": havefuncColor}})

    elif linkTo[-1] == "Function":

        nodes_trans.append({"id": 0, "name": sourceName, "category": 1, "colors": funcColor})
        # print(linkTo[0])
        for i in linkTo[0]:  # have_technology_of往外连
            # if i not in nodes_seen:  # 去重
            #     nodes_seen.append(i)
            nodes_trans.append({"id": curId, "name": i, "category": 2, "colors": techColor})

            curId += 1
            links_trans.append(
                {"source": 0, "target": curId - 1, "value": "have_technology_of", "lineStyle": {"color": havetechColor}})

        for i in linkTo[1]:  # have_function_of往里连
            # if i not in nodes_seen:  # 去重
            #     nodes_seen.append(i)
            nodes_trans.append({"id": curId, "name": i, "category": 0, "colors": susColor})  # 邻接点

            curId += 1
            links_trans.append(
                {"source": curId - 1, "target": 0, "value": "have_function_of", "lineStyle": {"color": havefuncColor}})

    else:  # 是Technology节点
        nodes_trans.append({"id": 0, "name": sourceName, "category": 2, "colors": funcColor})
        # print(linkTo[0])
        for i in linkTo[0]:  # have_technology_of往内连
            # if i not in nodes_seen:  # 去重
            #     nodes_seen.append(i)
            nodes_trans.append({"id": curId, "name": i, "category": 1, "colors": funcColor})

            curId += 1
            links_trans.append(
                {"source": curId - 1, "target": 0, "value": "have_technology_of",
                 "lineStyle": {"color": havetechColor}})

    # print((nodes_trans, links_trans))
    return (nodes_trans, links_trans)


def fuzzThreshold(lst, threshold):
    cnt = 0
    res = []
    for i in lst:
        if i[1] >= threshold:
            cnt += 1
            res.append(i[0])

    return cnt, res


def fuzzSearch(searchTxt, totalNum=12, threshold=60):

    funcCnt, funcRes = fuzzThreshold(process.extract(searchTxt, functionNode, limit=10), threshold)
    techCnt, techRes = fuzzThreshold(process.extract(searchTxt, technologyNode, limit=10), threshold)
    sustainCnt, sustainRes = fuzzThreshold(process.extract(searchTxt, sustainNode, limit=10), threshold)

    eachMeanNum = totalNum // 3

    res = []

    if funcCnt + techCnt + sustainCnt <= totalNum:  # 三个小
        res.append(funcRes)
        res.append(techRes)
        res.append(sustainRes)

    elif funcCnt > eachMeanNum and techCnt > eachMeanNum and sustainCnt > eachMeanNum:  # 三个大
        res.append(funcRes[:eachMeanNum])
        res.append(techRes[:eachMeanNum])
        res.append(sustainRes[:eachMeanNum])

    elif funcCnt < eachMeanNum and techCnt > eachMeanNum and sustainCnt > eachMeanNum:  # 小大大
        if techCnt - eachMeanNum >= eachMeanNum - funcCnt:
            res.append(funcRes)
            res.append(techRes[:2 * eachMeanNum - funcCnt])
            res.append(sustainRes[:eachMeanNum])
        else:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes[:3 * eachMeanNum - funcCnt - techCnt])

    elif funcCnt > eachMeanNum and techCnt < eachMeanNum and sustainCnt > eachMeanNum:  # 小大大
        if sustainCnt - eachMeanNum >= eachMeanNum - techCnt:
            res.append(funcRes)
            res.append(techRes[:2 * eachMeanNum - sustainCnt])
            res.append(sustainRes[:eachMeanNum])

        else:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes[:3 * eachMeanNum - techCnt - sustainCnt])

    elif funcCnt > eachMeanNum and techCnt > eachMeanNum and sustainCnt < eachMeanNum:  # 小大大
        if funcCnt - eachMeanNum >= eachMeanNum - sustainCnt:
            res.append(funcRes)
            res.append(techRes[:2 * eachMeanNum - funcCnt])
            res.append(sustainRes[:eachMeanNum])

        else:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes[:3 * eachMeanNum - sustainCnt - funcCnt])

    elif funcCnt < eachMeanNum and techCnt < eachMeanNum and sustainCnt > eachMeanNum:  # 小小大
        if 2 * eachMeanNum - funcCnt - techCnt <= sustainCnt - eachMeanNum:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes)

        else:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes[:3 * eachMeanNum - funcCnt - techCnt])

    elif funcCnt > eachMeanNum and techCnt < eachMeanNum and sustainCnt < eachMeanNum:  # 小小大
        if 2 * eachMeanNum - techCnt - sustainCnt <= funcCnt - eachMeanNum:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes)

        else:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes[:3 * eachMeanNum - techCnt - sustainCnt])

    elif funcCnt < eachMeanNum and techCnt > eachMeanNum and sustainCnt < eachMeanNum:  # 小小大
        if 2 * eachMeanNum - sustainCnt - funcCnt <= techCnt - eachMeanNum:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes)

        else:
            res.append(funcRes)
            res.append(techRes)
            res.append(sustainRes[:3 * eachMeanNum - sustainCnt - funcCnt])

    return res


app = Flask(__name__)


@app.route('/', methods=['POST', 'GET'])
def welcomePage():
    return render_template('main.html')  # , nodes_trans=json.dumps(nod[0]), links_trans=json.dumps(nod[1])


@app.route('/search', methods=['POST', 'GET'])
def searchPage():
    searchName = request.args.get('searchKeyword', 0, type=str)

    searchLst = fuzzSearch(searchName)

    return jsonify(funcNodes=searchLst[0], techNodes=searchLst[1], sustainNodes=searchLst[2])

    # res = neoapp.find_person(searchName, "have_function_of")
    # nod = dataFormatting(res, searchName)
    #
    # return jsonify(nodes_trans=nod[0], links_trans=nod[1])


    # return render_template('main.html', nodes_trans=json.dumps(nod[0]), links_trans=json.dumps(nod[1]))

@app.route('/searchdatabase', methods=['POST', 'GET'])
def searchDb():
    searchName = request.args.get('searchKeyword', 0, type=str)
    nodeType = request.args.get('type', 0, type=str)

    res = neoapp.find_person(searchName, nodeType)

    nod = dataFormatting(res, searchName)

    return jsonify(nodes_trans=nod[0], links_trans=nod[1])

    # return render_template('main.html', nodes_trans=json.dumps(nod[0]), links_trans=json.dumps(nod[1]))

@app.route('/refreshRecord', methods=['POST', 'GET'])
def refreshRecord():
    searchLst = fuzzSearch(global_var.get_value('dicTxt'), threshold=15)
    return jsonify(dicTxt=global_var.get_value('dicTxt'), funcNodes=searchLst[0], techNodes=searchLst[1], sustainNodes=searchLst[2])




if __name__ == '__main__':
    #初始化全局变量库
    global_var._init()

    # 连接数据库
    uri = "neo4j+s://712238d8.databases.neo4j.io"
    user = "neo4j"
    password = "S1lMM7FGmF1T6KUxYEOVU6V3EmppLjA0a7qZQ9FtCsQ"
    neoapp = App(uri, user, password)

    # 有三种类型的节点
    functionNode = ['农业环境信息采集',
                    '信息汇聚',
                    '温湿度调节',
                    '数据管理',
                    '数据存储',
                    '数据共享',
                    '供应链数据共享',
                    '应用系统',
                    '产品认证与追溯',
                    '农业可持续发展能力评价',
                    '地质环境评估',
                    '农业环境信息监测',
                    '干旱监测分析',
                    '农业水资源配置',
                    '农业节水',
                    '农业智能控制',
                    '虫害防治',
                    '农业能耗计算',
                    '健康档案管理',
                    '医学服务',
                    '仿声服务',
                    '视频交流服务',
                    '健康数据管理',
                    '用户预警',
                    '用户管理',
                    '健康数据采集',
                    '传染病检测结果鉴定',
                    '心理咨询',
                    '个性化诊疗',
                    '远程医疗',
                    '心理健康评估',
                    '心理健康管理',
                    '医疗决策',
                    '医嘱生成',
                    '慢性病风险评估',
                    '健康方案设计',
                    '智能化管理应答',
                    '传染病预测分析',
                    '心理监测',
                    '传染病监测',
                    '传染病防控追溯',
                    '心理压力分析',
                    '安全监护',
                    '一键求助',
                    '紧急求助',
                    '健康监测',
                    '医疗保健',
                    '传染病预警',
                    '健康服务',
                    '健康咨询',
                    '联网报警',
                    '心理健康预警',
                    '健康知识获取',
                    '健康干预',
                    '心理辅导',
                    '健康测试',
                    '智能理疗',
                    '远程教育',
                    '视频会议',
                    '教材页码定位',
                    '学习监督',
                    '答疑',
                    '课程管理',
                    '考勤',
                    '自测',
                    '在线讨论',
                    '作业答题',
                    '课程学习',
                    '多媒体教学',
                    '可持续发展教育评估',
                    '教育数据存储',
                    '教育资源共享',
                    '教学资源推荐',
                    '积分奖励',
                    '教学资源访问',
                    '教育资源分类',
                    '教学数据采集',
                    '供水管网管理',
                    '水流数据分析',
                    '水流数据采集',
                    '供水管网管理',
                    '供水情况分析',
                    '水质监测',
                    '重金属监测',
                    '水压检测',
                    '水质预警',
                    '水质数据采集',
                    '饮用水安全评估',
                    '水污染防控',
                    '水污染风险评估',
                    '水污染浓度计算',
                    '污染源确认',
                    '水质数据分析',
                    '智能充电',
                    '充电桩管理',
                    '电车充电能源分配',
                    '社区清洁能源管理',
                    '能源调度优化',
                    '电能动态分析',
                    '电量调控',
                    '电量监测',
                    '清洁能源监测',
                    '能源分配优化',
                    '能源利用效率优化',
                    '能源信息互联',
                    '电力调度',
                    '清洁能源信息采集',
                    '能源消费预测',
                    '清洁能源交易',
                    '电网规划',
                    '配电方案规划',
                    '发电数据分析',
                    '发电功率预测',
                    '发电实时监控',
                    '新能源车辆监测',
                    '游客数量采集',
                    '景区管理',
                    '自然灾害预警',
                    '人流量预警',
                    '人流疏导',
                    '景区参观',
                    '就业数据分析',
                    '课程规划分析',
                    '工作状态登记',
                    '就职请求',
                    '中介管理',
                    '企业信息管理',
                    '岗位招聘',
                    '岗位培训',
                    '就职信息查询',
                    '企业信息发布',
                    '手语翻译',
                    '手语客服',
                    '聋哑人安全提醒',
                    '盲人导航',
                    '手语识别',
                    '残疾人辅助智能驾驶',
                    '盲人视觉辅助',
                    '盲人行走辅助',
                    '聋哑人教学',
                    '聋哑人沟通',
                    '残疾人辅助行动',
                    '盲人手机操作',
                    '盲人室内导引',
                    '触屏手势识别',
                    '包容设计辅助',
                    '浇水量控制',
                    '浇水量显示',
                    '丢弃垃圾行为检测',
                    '垃圾分类积分激励',
                    '积分奖惩',
                    '垃圾箱安全检测',
                    '垃圾类别识别',
                    '垃圾棚灯光控制',
                    '垃圾桶充电',
                    '自动倾倒垃圾',
                    '垃圾装满检测',
                    '垃圾分类提醒',
                    '垃圾自动投放',
                    '垃圾投放预约',
                    '垃圾袋识别',
                    '垃圾上门收取',
                    '智慧城市可持续发展决策',
                    '智慧城市建设',
                    '公共信息服务',
                    '公共数据整合',
                    '公共数据组织',
                    '公共数据共享',
                    '公共信息决策',
                    '服务调度',
                    '厂商管理',
                    '资源库管理',
                    '数据安全授权',
                    '数据备份',
                    '故障通知',
                    '访问统计',
                    '运行监控',
                    '可视化管理',
                    '单车需求预测',
                    '骑行路线推荐',
                    '共享单车检测管理',
                    '服务区分配',
                    '单车管理人员分配',
                    '单车使用推荐',
                    '定位',
                    '路线规划',
                    '摆放角度检测',
                    '单车回收',
                    '历史数据收集',
                    '单车动态部署',
                    '单车搬运路径计算',
                    '文化遗产保护研究',
                    '文化展品交易',
                    '文化展示',
                    '文物聚集性分析',
                    '文物迁移性分析',
                    '纹样数字化处理',
                    '数字化采集',
                    '文化遗产修复',
                    '交通流量分配',
                    '订单数据采集',
                    '公交车数据采集',
                    '车辆能耗成本计算',
                    '车辆时间成本计算',
                    '车辆排放成本计算',
                    '车辆轨迹数据分析',
                    '信号灯配时',
                    '交通流量分配',
                    '交通道路规划',
                    '道路通行管理',
                    '道路动态定价',
                    '地图匹配',
                    '道路状态记录',
                    '行驶轨迹查询',
                    '道路通行权分配',
                    '物流配送路径计算',
                    '绿色运输',
                    '信息化监控',
                    '物资存储安全预警',
                    '物资存储',
                    '物资动态调度',
                    '物资运输方案设计',
                    '城市空间划分',
                    '城市空间预测',
                    '城乡发展预警',
                    '城市供暖资源分配',
                    '城市能源供需分配',
                    '电力优化',
                    '能源成本计算',
                    '环境成本计算',
                    '家电耗电数据采集',
                    '家电节电建议',
                    '家电耗电数据可视化',
                    '家电维修建议',
                    '碳排放检测',
                    '碳排放调节',
                    '产品碳足迹数据收集',
                    '产品碳足迹计算',
                    '产品碳足迹优化',
                    '产品碳足迹分析',
                    '产品数据采集',
                    '产品溯源',
                    '用户消费习惯分析',
                    '用户消费记录',
                    '低碳发展指数评价',
                    '碳排放行为数据收集',
                    '低碳任务提供',
                    '碳交易',
                    '碳账户',
                    '碳减排行为数据收集',
                    '碳管理平台',
                    '碳资源兑换',
                    '消费商户信息获取',
                    '低碳消费物品识别',
                    '低碳消费激励',
                    '绿色出行数据采集',
                    '公交里程数采集',
                    '志愿公益数据采集',
                    '汽车碳排放数据采集',
                    '公共服务资源激励',
                    '商业优惠折扣激励',
                    '社会公益激励',
                    '公共服务兑换',
                    '碳账户累计',
                    '用户碳排放量调控',
                    '发电碳排放量计算',
                    '用户碳排放量计算',
                    '电量数据采集',
                    '碳排放污染可视化',
                    '用电行为识别',
                    '用电设备监测',
                    '用电消费优化',
                    '用电行为分析',
                    '用电行为干预',
                    '碳中和项目推荐',
                    '企业碳排放计算',
                    '元件碳排放计算',
                    '个人碳足迹评估',
                    '智能家居能源监控',
                    '家电能耗分析',
                    '节能方案生成',
                    '家电运行控制',
                    '碳资产管理',
                    '能耗警报',
                    '节能减排数据管理',
                    '绿色产品认证',
                    '绿色产业链构建',
                    '绿色产品推荐',
                    '渔船监管',
                    '渔船信息采集',
                    '捕捞作业监测',
                    '海水水样采集',
                    '海洋环境观测',
                    '海水盐度监控',
                    '海水成分分析',
                    '海水生物种类识别',
                    '禁捕捞水印生成',
                    '海水生物禁捕信息存储',
                    '野生生物数据存储',
                    '生态保护成本计算',
                    '生态环境适宜性评价',
                    '生物保护价值计算',
                    '森林蓄积量分布估测',
                    '森林资源监测',
                    '土壤水分植被承载力计算',
                    '土壤肥力调控',
                    '家庭成员关系亲密度计算',
                    '家庭关系分析',
                    '家庭关系识别',
                    '家庭关系挖掘',
                    '家庭配偶关系预测']

    technologyNode = ['传感器设备',
                      '红外线设备',
                      '无人机',
                      '气体分析仪',
                      '物联网',
                      'GPS',
                      '单片机',
                      '动态定位算法',
                      '无线通信技术',
                      '继电器',
                      '分布式数据库系统',
                      '云计算',
                      '数学建模',
                      '无人机',
                      '反演模型',
                      '数据库',
                      'ET',
                      '智能芯片',
                      '图像处理',
                      '地理信息系统',
                      '线性规划算法',
                      '大数据分析',
                      '定位',
                      '身份识别',
                      '音像设备',
                      '机器人',
                      '自然语言处理',
                      '语音合成',
                      '语音识别',
                      '识别',
                      '数据管理',
                      '生理信号提取',
                      '可穿戴设备',
                      '电压计算',
                      '电流计算',
                      '图像采集',
                      '图像识别',
                      '边缘计算',
                      '云服务器',
                      '神经网络',
                      '机器学习',
                      '情感识别',
                      '情感模型',
                      '融合算法',
                      '卷积神经网络',
                      '情感计算',
                      '区块链',
                      '分布式传感器网络',
                      '协同感知算法',
                      '人工智能',
                      '语音机器人',
                      '智能家居',
                      '相似度计算',
                      '知识图谱',
                      '三维可视化技术',
                      '数据挖掘',
                      'RFID',
                      '聊天机器人',
                      '智能硬件',
                      '测试设备',
                      '智能硬件',
                      '情感计算',
                      '文本识别',
                      '语音识别',
                      '模式识别',
                      '图像情感分析',
                      '深度学习',
                      '语音情感识别',
                      '人机交互',
                      '5G',
                      '智能硬件',
                      '增强现实',
                      '视频编码',
                      '计算机图形学',
                      '多媒体技术',
                      '投影技术',
                      '回归计算',
                      '云架构',
                      '差值算法',
                      '水流量信号采集器',
                      '水流速信号采集器',
                      '数据存储',
                      '5G',
                      '模拟信号',
                      '遥感数据',
                      '数据存储',
                      '储能设备',
                      '发电设备',
                      '智能终端',
                      '双向计量算法',
                      '远程计算',
                      '供电设备',
                      '双向计量算法',
                      '电表',
                      '电压测量设备',
                      '电流测量设备',
                      '路由器',
                      'DDQN算法',
                      'H-CRAN网络',
                      '马尔可夫决策模型',
                      '分布式算法',
                      'GSM通信装置',
                      '云服务器',
                      '无线通信',
                      '算法',
                      '模糊算法',
                      '车载处理器',
                      '路线规划算法',
                      '虚拟现实',
                      '人脸识别',
                      '视频直播',
                      '三维建模',
                      '语音识别',
                      '微处理器',
                      '图像识别',
                      '视频识别',
                      'HMM',
                      'CRF',
                      'GAN',
                      'Kinect',
                      '聚类算法',
                      '脑电信息采集',
                      '长短期记忆神经网络',
                      '脉冲神经网络',
                      'EEGNet神经网络',
                      '语音识别',
                      '路径优化算法',
                      '目标检测',
                      '特征识别',
                      '计算机图形学',
                      '机器视觉技术',
                      '障碍物检测',
                      '目标检测',
                      '深度学习',
                      '三维建模',
                      '点云特征',
                      '欧几里得算法',
                      '激光雷达',
                      '机械臂',
                      '脑电信息采集',
                      '手势识别',
                      '焦点标记',
                      '语音识别',
                      '目标检测',
                      '超声波探测',
                      '动作识别',
                      '隐马尔可夫模型算法',
                      '手指识别算法',
                      '行为识别',
                      '硬件处理器',
                      '智能生成',
                      '处理器',
                      '电磁阀',
                      '水流量计',
                      '人体特征检测',
                      '人脸识别',
                      '特征提取',
                      '红外线设备',
                      '超声波探测',
                      '红外线设备',
                      '自动化',
                      '结构方程模型',
                      '回归计算',
                      '数据传输',
                      '协议转换',
                      '数据格式转换',
                      '适配器',
                      '数据链接技术',
                      '路由器',
                      '数据链接技术',
                      '算法',
                      '信息安全',
                      '图数据库',
                      '前端开发',
                      '贝叶斯时空模型',
                      'INLA算法',
                      '数据采集',
                      '路径计算算法',
                      '目标检测',
                      '算法',
                      '拓扑算法',
                      '路径计算算法',
                      'RFID',
                      '最优路径算法',
                      '单车动态调度算法',
                      '优化算法',
                      '启发式算法',
                      '禁忌搜索算法',
                      '文化基因算法',
                      '遗传算法',
                      '领域搜索算法',
                      '识别技术',
                      '5G通信',
                      'pagerank算法',
                      '余弦相似度计算',
                      '标准差椭圆算法',
                      '编码',
                      '图像识别',
                      '深度学习',
                      '数据细粒度匹配',
                      '数据采集传输器',
                      '静载应变计',
                      '熵权法',
                      '轨迹分析',
                      '坐标系转换法',
                      '有向路径算法',
                      '生态指数计算算法',
                      '有向路径计算算法',
                      '流量计算算法',
                      '防碰撞探测器',
                      '自动化',
                      'RFID',
                      '路径计算算法',
                      '优化算法',
                      '作用力模型',
                      '置信度计算算法',
                      '多层循环算法',
                      '多级供暖方法',
                      '线性动态规划算法',
                      '电力监测仪',
                      '蓝牙设备',
                      '数据可视化',
                      '二氧化碳检测器',
                      '云服务器',
                      '碳排放基准线计算',
                      '处理器',
                      '粒子群算法',
                      '二维码',
                      'web GIS',
                      '差异赋权法',
                      '模糊变换',
                      '新能源发电设施',
                      '回收节能装置',
                      '采集计量设备',
                      '图像匹配算法',
                      '智能电表',
                      '电网控制系统',
                      '电源模型计算',
                      '曲线拟合算法',
                      '算法',
                      '云服务器',
                      '电能计量单元',
                      '微控制器',
                      '曲线计算算法',
                      '电厂集散控制系统',
                      'EMS（能量管理系统）',
                      '交互终端',
                      '数据建模',
                      '模型识别',
                      '序列算法',
                      '时间序列模型',
                      '智能配单算法匹配',
                      '碳中和一体化算法',
                      '碳中和一体化算法',
                      '标识管理仪器',
                      '位置监测装置',
                      '人脸识别',
                      '轨迹生成',
                      '活动时间序列测算算法',
                      '太阳能设备',
                      '条形码读取器',
                      '电子趋鱼装置',
                      '点云特征',
                      '逻辑回归',
                      '特征提取']

    sustainNode = ['无贫穷',
                   '零饥饿',
                   '良好健康与福祉',
                   '优质教育',
                   '性别平等',
                   '清洁饮水和卫生设施',
                   '经济适用的清洁能源',
                   '体面工作和经济增长',
                   '产业，创新和基础设施',
                   '减少不平等',
                   '可持续城市和社区',
                   '负责任消费和生产',
                   '气候行动',
                   '水下生物',
                   '陆地生物',
                   '和平，正义与强大机构',
                   '促进目标实现的伙伴关系',
                   '消除极端贫困',
                   '贫困人群至少减半',
                   '更大覆盖面的社保制度',
                   '保护穷人与弱势群体权益',
                   '增强穷人与弱势群体抵御灾害能力',
                   '国际帮助',
                   '国家消贫政策',
                   '消除饥饿',
                   '消除一切形式的营养不良',
                   '农业生产力增强',
                   '可持续农业发展',
                   '种子植物等生物遗传库知识',
                   '农业技术开发与基础设施建立',
                   '农产品出口',
                   '粮食价格稳定',
                   '孕妇生产安全',
                   '新生儿安全',
                   '传染病消除',
                   '传染病防治',
                   '心理健康与慢性疾病防治',
                   '药物与酒精滥用控制',
                   '交通事故预防',
                   '生殖健康服务',
                   '保健健康服务',
                   '环境安全',
                   '烟草控制',
                   '药品与疫苗生产管理',
                   '国家健康风险管控与预警',
                   '提供公平的中小学教育',
                   '优质的学前教育',
                   '优质的职业与高等教育',
                   '提升技术性和职业性技能',
                   '消除教育不平等',
                   '识字与计算能力',
                   '可持续发展教育',
                   '教育设施与学习环境建设',
                   '教育资金投入',
                   '教育师资培养',
                   '消除性别歧视',
                   '消除针对女性的暴力行为',
                   '消除童婚',
                   '提倡家庭责任共担',
                   '为女性提供平等社会地位',
                   '女性生殖健康',
                   '为女性提供平等经济地位',
                   '加强信息通讯技术应用',
                   '国家政策促进性别平等',
                   '饮用水安全',
                   '水环境卫生',
                   '减少管控水污染',
                   '用水效率提升',
                   '水资源综合管理',
                   '水生态系统保护',
                   '政府水治理技术发展',
                   '增强地方环境卫生管理',
                   '提供可用的现代能源服务',
                   '提倡可再生能源使用',
                   '能源能效改善',
                   '清洁能源技术研究',
                   '可持续能源服务及基础设施建设',
                   '人均国内生产总值增长',
                   '更高水平的经济生产力',
                   '支持创新创业',
                   '可持续消费',
                   '平等工作机会与报酬',
                   '提升青年人就业率',
                   '消除强制劳动与童工',
                   '保护劳工权利建设有保障的工作环境',
                   '可持续旅游',
                   '加强金融服务能力',
                   '促贸援助',
                   '青年就业战略实施',
                   '发展优质的城市基础设施',
                   '可持续工业化',
                   '发展小型工业的金融服务',
                   '清洁生产',
                   '提升工业技术能力',
                   '用于基础设施的国际援助',
                   '发展高科技产业',
                   '提升信息与通信技术普及度',
                   '维持底层人口收入增长',
                   '无论性别，年龄，残疾与否增强其权能',
                   '消除歧视',
                   '发展财政与社会保障政策',
                   '改善金融市场监管',
                   '提升发展中国在经济决策中的发言权',
                   '移民政策完善',
                   '落实联合国贸易无差别待遇',
                   '国际援助',
                   '减少移民汇款手续费',
                   '改善住房环境，改造贫民窟',
                   '可持续交通运输（共享）',
                   '可持续交通运输（物流）',
                   '可持续交通运输（交通）',
                   '可持续城市建设',
                   '保护文化与自然遗产',
                   '增强抵御自然灾害能力',
                   '城市环境改善与城市废物管理',
                   '提供安全包容便利与绿色的公共空间',
                   '城乡规划',
                   '灾害风险管理',
                   '可持续建筑',
                   '可持续生产',
                   '可持续消费',
                   '减少食物浪费',
                   '无害环境管理',
                   '减少废物产生，提高废物回收率',
                   '鼓励公司发布可持续报告',
                   '可持续的公共采购',
                   '可持续发展教育',
                   '科学技术支持可持续生产与消费',
                   '促进可持续旅游业发展',
                   '化石燃料补贴',
                   '增强抵御自然灾害能力',
                   '应对气候变化纳入政策',
                   '加强气候问题的宣传教育',
                   '履行《联合国气候变化框架公约》',
                   '促进不发达国家管理规划气候变化',
                   '减少海洋污染',
                   '保护海洋生态',
                   '减少海洋酸化',
                   '规范捕捞活动',
                   '建立海洋保护区',
                   '打击非法捕捞',
                   '可持续利用海洋资源',
                   '加强海洋技术研究',
                   '保护小规模渔业',
                   '立法保护海洋资源及其可持续利用',
                   '森林与陆地生态系统保护',
                   '可持续森林管理',
                   '防治荒漠化',
                   '保护山地生态系统',
                   '保护生物多样性',
                   '公平分享利用遗传资源产生的利益',
                   '打击非法野生生物贸易',
                   '防止外来入侵物种',
                   '将生态系统与生物多样性纳入国家政策',
                   '投资保护生态环境',
                   '激励可持续森林管理',
                   '打击偷猎与贩卖受保护物种',
                   '减少暴力行为',
                   '制止虐待，贩卖儿童行为',
                   '司法平等',
                   '打击有组织犯罪',
                   '减少腐败贿赂',
                   '建立透明负责的行政体系',
                   '确保各级决策',
                   '加强发展中国家对国际事务的参与',
                   '法律身份',
                   '保障公民知情权',
                   '打击恐怖主义与犯罪行为',
                   '推动非歧视性法律',
                   '向发展中国家提供国际支持',
                   '发达国家履行援助承诺',
                   '筹集额外财政资源用于发展中国家',
                   '实现发展中国家长期债务可持续性',
                   '对发展中国家实施投资促进制度',
                   '加强科技合作',
                   '优惠的促进开发，转让传播和推广技术',
                   '帮助发展中国家加强信息和通信技术',
                   '全球加权平均关税',
                   '增加发展中国家出口',
                   '鼓励不发达国家产品进入市场',
                   '宏观经济信息汇总',
                   '可持续发展政策一致性',
                   '尊重各国政策',
                   '加强全球可持续发展伙伴关系 加强全球可持续发展伙伴关系，以多利益攸关方伙伴关系作为补充，调动和分享知识、专长、技术和财政资源，以支持所有国家、尤其是发展中国家实现可持续发展目标 183',
                   '鼓励和推动建立有效的公共、公私和民间社会伙伴关系',
                   '可持续发展目标数据收集',
                   '可持续发展目标监测的统计能']

    app.run(port=5006, debug=True)

    dictation()
