# Pseudocode — Frontend: Prices & Reviews Pages

---

## prices.ts API Client

```
FUNCTION cleanParams(obj):
  RETURN entries where value != null AND value != undefined

EXPORT pricesApi:
  latest(skuId): GET /prices/latest?sku_id=skuId → PriceLatestResponse
  anomalies(skuId, dateFrom?, dateTo?, threshold?): GET /prices/anomalies + cleanParams
  history(skuId, platformId?, dateFrom?, dateTo?): GET /prices/history + cleanParams
  stats(skuId, platformId?, dateFrom?, dateTo?): GET /prices/stats + cleanParams
```

## reviews.ts API Client

```
EXPORT reviewsApi:
  summary(skuId, dateFrom?, dateTo?): GET /reviews/summary + cleanParams
  history(skuId, platform?, sentiment?, dateFrom?, dateTo?, limit, offset): GET /reviews/history
  stats(skuId, dateFrom?, dateTo?): GET /reviews/stats + cleanParams
```

## PricesPage Component

```
STATE: skuId, dateRange ([30 days ago, today]), platformId

QUERY skus: useQuery(['skus-list'], skusApi.list, staleTime=10min)
QUERY latest: useQuery(['prices-latest', skuId], () => pricesApi.latest(skuId), enabled=!!skuId)
QUERY anomalies: useQuery(['prices-anomalies', skuId, dateFrom, dateTo], enabled=!!skuId)
QUERY history: useQuery(['prices-history', skuId, platformId, dateFrom, dateTo], enabled=!!skuId)
QUERY stats: useQuery(['prices-stats', skuId, platformId, dateFrom, dateTo], enabled=!!skuId)

RENDER:
  <Title> Price Monitoring </Title>
  <Row>
    <SKU Select: options from skus query>
    <DatePicker.RangePicker: default last 30 days>
  </Row>

  IF !skuId: <Empty description="Select a SKU to view prices"/>

  ELSE:
    <Row gutter=16>  // Stats cards
      FOR stat IN [min, max, avg, change_pct]:
        <StatCard value=stats[stat] loading=stats.isLoading/>
    </Row>

    <Title level=4> Latest Prices </Title>
    <Table
      columns=[Platform, Price, Original, Discount%, Promo, Cheapest, Updated]
      rowClassName: IF row.platform_id == cheapest_platform_id → 'row-green'
    />

    <Title level=4> Price Anomalies </Title>
    <Row> <Select platform filter> <DatePicker range> </Row>
    <Table
      columns=[Platform, Date, Before, After, Change, Direction]
      direction render: IF 'down' → <span red>↓ change_pct%</span>
                        IF 'up'  → <span green>↑ change_pct%</span>
    />

    <Title level=4> Price History </Title>
    <Select platform (optional)>
    <ReactECharts option=buildHistoryChart(history.items)/>

FUNCTION buildHistoryChart(items):
  GROUP items by platform_name → series[]
  RETURN {
    xAxis: { type: 'category', data: unique dates }
    yAxis: { type: 'value', axisLabel: '₽' }
    series: [{ name: platform, type: 'line', data: prices }]
    tooltip: { trigger: 'axis' }
    legend: { bottom: 0 }
  }
```

## ReviewsPage Component

```
STATE: skuId, dateRange, sentimentFilter, reviewPage (offset=page*100)

QUERY skus: useQuery(['skus-list'], staleTime=10min)
QUERY summary: useQuery(['reviews-summary', skuId, dateFrom, dateTo], enabled=!!skuId)
QUERY stats: useQuery(['reviews-stats', skuId, dateFrom, dateTo], enabled=!!skuId)
QUERY history: useQuery(['reviews-history', ...all filters], enabled=!!skuId)

RENDER:
  <Title> Reviews & Sentiment </Title>
  <Row>
    <SKU Select>
    <DatePicker.RangePicker>
  </Row>

  IF !skuId: <Empty/>

  ELSE:
    <Row gutter=16>
      <Col span=12>  // Sentiment pie
        <ReactECharts option=buildSentimentPie(stats.data)/>
      </Col>
      <Col span=12>  // Overall stats cards
        <Statistic title="Total Reviews" value=stats.data.review_count/>
        <Statistic title="Avg Rating" value=stats.data.avg_rating prefix=<StarFilled/>/>
      </Col>
    </Row>

    <Title level=4> By Platform </Title>
    <Table
      columns=[Platform, Reviews, Avg Rating, Positive%, Neutral%, Negative%, Last Review]
      render positive_pct: <Progress percent=pct status='success'/>
      render negative_pct: <Progress percent=pct status='exception'/>
    />

    <Title level=4> Weekly Trend </Title>
    <ReactECharts option=buildTrendChart(stats.data.weekly_trend)/>

    <Title level=4> Individual Reviews </Title>
    <Space>
      <Select sentiment: All / Positive / Neutral / Negative>
      <Select platform (optional)>
    </Space>
    <Table
      columns=[Date, Platform, Rating, Sentiment, Review Text]
      pagination={pageSize:100, total:history.total, onChange: setReviewPage}
      sentiment render: IF null → <Tag>Pending</Tag>
                        IF positive → <Tag color='success'>Positive</Tag>
                        IF neutral  → <Tag color='default'>Neutral</Tag>
                        IF negative → <Tag color='error'>Negative</Tag>
      rating render: <Rate disabled value=rating/>
    />

FUNCTION buildSentimentPie(stats):
  IF !stats?.sentiment_share: RETURN empty config
  RETURN {
    series: [{
      type: 'pie', radius: ['40%','70%'],
      data: [
        { name:'Positive', value: sentiment_share.positive, itemStyle:{color:'#52c41a'}},
        { name:'Neutral',  value: sentiment_share.neutral,  itemStyle:{color:'#8c8c8c'}},
        { name:'Negative', value: sentiment_share.negative, itemStyle:{color:'#ff4d4f'}},
      ]
    }]
  }

FUNCTION buildTrendChart(trend):
  RETURN {
    xAxis: { type:'category', data: trend.map(t => t.week_start) }
    yAxis: { type:'value', max:100, axisLabel:'{value}%' }
    series: [{ type:'bar', data: trend.map(t => t.positive_share), itemStyle:{color:'#52c41a'}}]
    tooltip: { formatter: '{b}: {c}% positive' }
  }
```
