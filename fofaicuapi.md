## 系统简介

本系统是FOFA的中转代理平台，支持在线**网页查询**和**API查询**，其中**API查询接口调用方式与官网完全一致**，并且兼容各种第三方查询工具。

==使用第三方工具时，只需要将官网的api地址换成本站的api地址（====`http://fofa.icu`====）即可。11==

## API 概览

本系统提供以下API接口：

1. **搜索接口** (`/api/v1/search/all`) - 与 FOFA 搜索功能对应
2. **连续翻页接口** (`/api/v1/search/next`) - 支持大数据持续获取
3. **统计数据接口** (`/api/v1/search/stats`) - 获取查询结果统计信息
4. **Host查询接口** (`/api/v1/host/{host}`) - 获取指定主机的详细信息
5. **用户信息接口** (`/api/v1/info/my`) - 获取API密钥状态和剩余配额

## 配额限制

- 普通搜索接口（`/api/v1/search/all`）消耗与返回结果数量相等的查询配额
- 统计聚合接口（`/api/v1/search/stats`）固定消耗10,000个查询配额
- Host查询接口（`/api/v1/host/{host}`）固定消耗1,000个查询配额
- 用户信息接口（`/api/v1/info/my`）不消耗查询配额

## 每日查询限制

- **每个API密钥每天只能查询500次，并发5s一次**
- 用户信息接口（`/api/v1/info/my`）不计入每日查询限制
- 每日限制在北京时间0点（UTC+8）重置
- 超过每日限制将返回错误代码-703


## 个人信息接口

可以查看当前账号的状态、email、用户名、余额、会员等级等基础信息。注：没有查询数据。

```
curl -X GET "http://fofa.icu/api/v1/info/my?key=your_key"
```

响应示例：

```
{
  "error": false,
  "email": "test@qq.com",  
  "username": "vip",  
  "category": "user",  
  "fcoin": 0,  
  "fofa_point": 0,  
  "remain_free_point": 0,  
  "remain_api_query": 1000,  // key的剩余查询数量
  "remain_api_data": -1,  
  "isvip": true,  // key的有效状态
  "vip_level": 999,  
  "is_verified": false,  
  "avatar": "https://nosec.org/missing.jpg",  
  "message": "",  
  "fofacli_ver": "4.0.3",  
  "fofa_server": true,  
  "expiration": "2025-04-09"  // key的过期时间
}
```

## 统计聚合

根据当前的查询内容，生成全球统计信息，当前可统计每个字段的前5排名。该接口限制请求并发为 5秒/次。

```GET
http://fofa.icu/api/v1/search/statsGETcontent_copy
```

| 序号 | 参数    | 必填 | 类型   | 描述                                         | 示例                     |
| ------ | --------- | ------ | -------- | ---------------------------------------------- | -------------------------- |
| 1    | qbase64 | 是   | string | 经过base64编码后的查询语法，即输入的查询内容 | aXA9IjEwMy4zNS4xNjguMzgi |
| 2    | fields  | 否   | string |                                              |                          |

附录2：统计聚合接口支持的字段，按照示例配置 fields\=protocol,domain,port 即可。

| 序号 | 字段名         | 描述            | 权限 |
| ------ | ---------------- | ----------------- | ------ |
| 1    | protocol       | 协议            | 无   |
| 2    | domain         | 域名            | 无   |
| 3    | port           | 端口            | 无   |
| 4    | title          | http 标题       | 无   |
| 5    | os             | 操作系统        | 无   |
| 6    | server         | http server信息 | 无   |
| 7    | country        | 国家、城市统计  | 无   |
| 8    | asn            | asn编号         | 无   |
| 9    | org            | asn组织         | 无   |
| 10   | asset\_type | 资产类型        | 无   |
| 11   | fid            | fid 统计        | 无   |
| 12   | icp            | icp备案信息     | 无   |

返回结果字段:

| 功能名   | 描述     | 支持字段说明                              |
| ---------- | ---------- | ------------------------------------------- |
| distinct | 唯一计数 | 支持字段: server, icp, domain, title, fid |
| aggs     | 聚合信息 | 通用                                      |

FOFA API支持cURL、Python、Java、Go语言的请求，以cURL为例：

```bash
curl -X GET "http://fofa.icu/api/v1/search/stats?fields=title&qbase64=dGl0bGU9IueZvuW6piI%3D&key=your_key"bashcontent_copy
```

 响应示例：

```json
{
  "error": false, // 是否出现错误
  "consumed_fpoint": 0, // 实际F点
  "required_fpoints": 0, // 应付F点
  "size": 4277422, // 查询总数量
  "distinct": {
    "ip": 32933,
    "title": 82280
  },
  "aggs": {
    "title": [
        {
            "count": 76234,
            "name": "网站未备案或已被封禁——百度智能云云主机管家服务"
        },
        {
            "count": 50220,
            "name": "百度一下, 你就知道"
        },
        {
            "count": 39532,
            "name": "百度热榜"
        },
        {
            "count": 37177,
            "name": "百度 H5 - 真正免费的 H5 页面制作平台"
        },
        {
            "count": 33986,
            "name": "百度SEO"
        }
    ]
  },
  "lastupdatetime": "2022-05-23 15:00:00"
}
```


## Host聚合

根据当前的查询内容，生成聚合信息，host通常是ip，包含基础信息和IP标签。该接口限制请求并发为 1s/次。

```GET
http://fofa.icu/api/v1/host/{host}GETcontent_copy
```

| 序号 | 参数   | 必填 | 类型    | 描述             | 示例         |
| ------ | -------- | ------ | --------- | ------------------ | -------------- |
| 1    | host   | 是   | string  | host名，通常是ip | 78.48.50.249 |
| 2    | detail | 否   | boolean | 显示端口详情     | false        |

当detail\=false时，默认为普通模式，以cURL为例：

```bash
curl -X GET "http://fofa.icu/api/v1/host/78.48.50.249?&key=your_key"bashcontent_copy
```

响应示例：

```json
{
  "error": false,
  "host": "78.48.50.249",
  "ip": "78.48.50.249",
  "consumed_fpoint": 0, // 实际F点
  "required_fpoints": 0, // 应付F点
  "asn": 6805,
  "org": "Telefonica Germany",
  "country_name": "Germany",
  "country_code": "DE",
  "protocol": [
    "sip",
    "http",
    "https"
  ],
  "port": [
    500,
    443,
    80,
    7170,
    5060,
    8089
  ],
  "category": [
    "服务",
    "操作系统"
  ],
  "product": [
    "gSOAP",
    "FRITZ!OS"
  ],
  "update_time": "2023-08-23 02:00:00"
}jsoncontent_copy
```

返回结果字段:

| 字段名   | 描述     |
| ---------- | ---------- |
| port     | 端口列表 |
| protocol | 协议列表 |
| domain   | 域名列表 |
| category | 分类标签 |
| product  | 产品标签 |

当detail\=true时，默认为详情模式，以cURL为例：

```bash
curl -X GET "http://fofa.icu/api/v1/host/78.48.50.249?detail=true&key=your-key"bashcontent_copy
```

响应示例：

```json
{
"error": false,
  "host": "78.48.50.249",
  "ip": "78.48.50.249",
  "asn": 6805,
  "org": "Telefonica Germany",
  "country_name": "Germany",
  "country_code": "DE",
  "ports": [
    {
      "port": 8089,
      "protocol": "http"
    },
    {
      "port": 7170,
      "protocol": "http"
    },
    {
      "port": 443,
      "protocol": "https",
      "products": [
        {
          "product": "Synology-WebStation",
          "category": "Content Management System (CMS)",
          "level": 5,
          "sort_hard_code": 2
        }
      ]
    },
    {
      "port": 5060,
      "protocol": "sip"
    }
  ],
  "update_time": "2023-05-24 12:00:00"
}jsoncontent_copy
```

返回结果字段:

| 字段名                 | 描述                                                                     |
| ------------------------ | -------------------------------------------------------------------------- |
| products               | 产品详情列表                                                             |
| product                | 产品名                                                                   |
| category               | 产品分类                                                                 |
| level                  | 产品分层：5 应用层，4 支持层，3 服务层，2 系统层，1 硬件层，0 无组件分层 |
| soft\_hard\_code | 产品是否为硬件；值为 1 是硬件，否则为非硬件                              |

## 查询接口

提供搜索主机、获取详细信息的方法，使开发更容易。

```GET
http://fofa.icu/api/v1/search/allGETcontent_copy
```

| 序号 | 参数       | 必填 | 类型    | 描述                                             | 示列                     |
| ------ | ------------ | ------ | --------- | -------------------------------------------------- | -------------------------- |
| 1    | qbase64    | 是   | string  | 经过base64编码后的查询语法，即输入的查询内容     | aXA9IjEwMy4zNS4xNjguMzgi |
| 2    | fields     | 否   | string  | 可选字段，默认host,ip,port，详见附录1            | host,ip,port             |
| 3    | page       | 否   | int     | 是否翻页，默认为第一页，按照更新时间排序         | 1                        |
| 4    | size       | 否   | int     | 每页查询数量，默认为100条，最大支持10,000条/页   | 100                      |
| 5    | full       | 否   | boolean | 默认搜索一年内的数据，指定为true即可搜索全部数据 | false                    |
| 6    | r\_type | 否   | string  | 可以指定返回json格式的数据                       | json                     |

附录1：查询接口支持的字段，按照示例配置 fields\=ip,host,port 即可。

| 序号 | 字段名               | 描述                           |
| ------ | ---------------------- | -------------------------------- |
| 1    | ip                   | IP地址                         |
| 2    | port                 | 端口                           |
| 3    | protocol             | 协议名                         |
| 4    | country              | 国家代码                       |
| 5    | country\_name     | 国家名                         |
| 6    | region               | 区域                           |
| 7    | city                 | 城市                           |
| 8    | longitude            | 地理位置 经度                  |
| 9    | latitude             | 地理位置 纬度                  |
| 10   | asn                  | ASN编号                        |
| 11   | org                  | ASN组织                        |
| 12   | host                 | 主机名                         |
| 13   | domain               | 域名                           |
| 14   | os                   | 操作系统                       |
| 15   | server               | 网站Server                     |
| 16   | icp                  | ICP备案号                      |
| 17   | title                | 网站标题                       |
| 18   | jarm                 | JARM指纹                       |
| 19   | header               | 网站Header                     |
| 20   | banner               | 协议Banner                     |
| 21   | cert                 | 证书                           |
| 22   | base\_protocol    | 基础协议，比如TCP/UDP          |
| 23   | link                 | 资产的URL链接                  |
| 24   | cert.issuer.org      | 证书颁发者组织                 |
| 25   | cert.issuer.cn       | 证书颁发者通用名称             |
| 26   | cert.subject.org     | 证书持有者组织                 |
| 27   | cert.subject.cn      | 证书持有者通用名称             |
| 28   | tls.ja3s             | JA3S指纹信息                   |
| 29   | tls.version          | TLS协议版本                    |
| 30   | cert.sn              | 证书的序列号                   |
| 31   | cert.not\_before  | 证书生效时间                   |
| 32   | cert.not\_after   | 证书到期时间                   |
| 33   | cert.domain          | 证书中的根域名                 |
| 34   | header\_hash      | HTTP/HTTPS响应信息计算的Hash值 |
| 35   | banner\_hash      | 协议响应信息的完整Hash值       |
| 36   | banner\_fid       | 协议响应信息架构的指纹值       |
| 37   | product              | 产品名                         |
| 38   | product\_category | 产品分类                       |
| 39   | version              | 版本号                         |
| 40   | lastupdatetime       | FOFA最后更新时间               |
| 41   | cname                | 域名CNAME                      |

FOFA API支持cURL、Python、Java、Go语言的请求，以cURL为例：

```bash
curl -X GET "http://fofa.icu/api/v1/search/all?&key=your_key&qbase64=dGl0bGU9ImJpbmci"bashcontent_copy
```

响应示例：

```json
{
    "error": false, // 是否出现错误
    "consumed_fpoint": 0,
    "required_fpoints": 0,
    "size": 244569, // 查询总数量
    "page": 1, // 当前页码
    "mode": "extended",
    "query": "title=\"bing\"", // 查询语句
    "results": [
      [
          "https://bingchillin.org",
          "172.67.213.134",
          "443"
      ],
      [
          "bingchillin.org",
          "104.21.69.223",
          "80"
      ],
      [
          "76.158.236.234:8080",
          "76.158.236.234",
          "8080"
      ],
      [
          "srkpixelsoft.com",
          "43.225.55.146",
          "80"
      ],
      [
          "https://srkpixelsoft.com",
          "43.225.55.146",
          "443"
      ],
      [
          "www.srkpixelsoft.com",
          "43.225.55.146",
          "80"
      ],
      [
          "https://www.srkpixelsoft.com",
          "43.225.55.146",
          "443"
      ],
      [
          "3.10.194.226",
          "3.10.194.226",
          "80"
      ],
      [
          "3.104.212.139",
          "3.104.212.139",
          "80"
      ]
    ]
  }
```
