import { useState, useEffect, useCallback } from 'react'
import { fetchHeatmap, fetchDrift, fetchWorkers, fetchStreamStats } from './dashboardApi'

function ConfigHeatmap({ data }) {
  if (!data || !data.cells.length) {
    return <div className="dashboard-empty">暂无热力图数据</div>
  }

  const getColor = (ratio) => {
    if (ratio <= 0.5) {
      const r = Math.round(82 + (250 - 82) * ratio * 2)
      const g = Math.round(196 - (196 - 173) * ratio * 2)
      const b = Math.round(26 + (20 - 26) * ratio * 2)
      return `rgba(${r}, ${g}, ${b}, 0.85)`
    }
    const t = (ratio - 0.5) * 2
    const r = Math.round(250 + (255 - 250) * t)
    const g = Math.round(173 - (173 - 77) * t)
    const b = Math.round(20 + (79 - 20) * t)
    return `rgba(${r}, ${g}, ${b}, 0.85)`
  }

  return (
    <div className="heatmap-container">
      <div
        className="heatmap-grid"
        style={{
          gridTemplateColumns: `120px repeat(${data.kernel_versions.length}, 1fr)`,
          gridTemplateRows: `40px repeat(${data.models.length}, 52px)`,
        }}
      >
        <div className="heatmap-corner">型号 \ 内核</div>
        {data.kernel_versions.map((kv) => (
          <div className="heatmap-col-header" key={kv}>{kv}</div>
        ))}
        {data.models.map((model) => (
          <>
            <div className="heatmap-row-header" key={`row-${model}`}>{model}</div>
            {data.kernel_versions.map((kv) => {
              const cell = data.cells.find((c) => c.model === model && c.kernel_version === kv)
              return (
                <div
                  key={`${model}-${kv}`}
                  className="heatmap-cell"
                  style={{ backgroundColor: cell ? getColor(cell.drift_ratio) : '#f0f0f0' }}
                  title={cell ? `${cell.count} 台设备, ${(cell.drift_ratio * 100).toFixed(0)}% 漂移` : '无设备'}
                >
                  {cell ? cell.count : '-'}
                </div>
              )
            })}
          </>
        ))}
      </div>
      <div className="heatmap-legend">
        <span className="legend-label">漂移程度:</span>
        <span className="legend-item" style={{ backgroundColor: 'rgba(82, 196, 26, 0.85)' }}>0%</span>
        <span className="legend-item" style={{ backgroundColor: 'rgba(250, 173, 20, 0.85)' }}>50%</span>
        <span className="legend-item" style={{ backgroundColor: 'rgba(255, 77, 79, 0.85)' }}>100%</span>
      </div>
    </div>
  )
}

function DriftTable({ data, skip, limit, onPageChange, driftedOnly, onFilterChange }) {
  if (!data) return null

  const totalPages = Math.ceil(data.total_devices / limit)
  const currentPage = Math.floor(skip / limit) + 1

  return (
    <div className="drift-section">
      <div className="drift-stats">
        <div className="drift-stat">
          <span className="stat-value drift-red">{data.drifted_count}</span>
          <span className="stat-label">配置漂移</span>
        </div>
        <div className="drift-stat">
          <span className="stat-value drift-green">{data.compliant_count}</span>
          <span className="stat-label">配置一致</span>
        </div>
        <div className="drift-stat">
          <span className="stat-value drift-gray">{data.unbound_count}</span>
          <span className="stat-label">未绑定模板</span>
        </div>
      </div>

      <div className="drift-filter">
        <label>
          <input
            type="checkbox"
            checked={driftedOnly}
            onChange={(e) => onFilterChange(e.target.checked)}
          />
          仅显示漂移设备
        </label>
      </div>

      <table className="drift-table">
        <thead>
          <tr>
            <th>设备ID</th>
            <th>型号</th>
            <th>绑定模板</th>
            <th>期望哈希</th>
            <th>当前哈希</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {data.devices.map((d) => (
            <tr key={d.device_id} className={d.is_drifted ? 'drift-row' : ''}>
              <td>{d.device_id}</td>
              <td>{d.model}</td>
              <td>{d.template_name || '-'}</td>
              <td className="hash-cell">{d.expected_hash ? d.expected_hash.slice(0, 12) + '...' : '-'}</td>
              <td className="hash-cell">{d.current_hash ? d.current_hash.slice(0, 12) + '...' : '-'}</td>
              <td>
                {d.is_drifted ? (
                  <span className="badge badge-drift">漂移</span>
                ) : d.expected_hash ? (
                  <span className="badge badge-ok">一致</span>
                ) : (
                  <span className="badge badge-unbound">未绑定</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="drift-pagination">
        <button disabled={currentPage <= 1} onClick={() => onPageChange(skip - limit)}>上一页</button>
        <span>第 {currentPage} 页</span>
        <button disabled={data.devices.length < limit} onClick={() => onPageChange(skip + limit)}>下一页</button>
      </div>
    </div>
  )
}

function WorkerStatus({ workers, streamStats }) {
  return (
    <div className="worker-section">
      <div className="worker-stats">
        <div className="drift-stat">
          <span className="stat-value">{workers?.active_workers || 0}</span>
          <span className="stat-label">活跃Worker</span>
        </div>
        <div className="drift-stat">
          <span className="stat-value">{streamStats?.stream_length || 0}</span>
          <span className="stat-label">Stream消息数</span>
        </div>
        <div className="drift-stat">
          <span className="stat-value">
            {streamStats?.groups?.[0]?.pending || 0}
          </span>
          <span className="stat-label">待处理消息</span>
        </div>
      </div>
      {workers?.workers?.length > 0 && (
        <table className="drift-table worker-table">
          <thead>
            <tr>
              <th>Worker名称</th>
              <th>最后心跳</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {workers.workers.map((w) => (
              <tr key={w.name}>
                <td>{w.name}</td>
                <td>{w.last_heartbeat || '-'}</td>
                <td>
                  <span className={`badge ${w.is_alive ? 'badge-ok' : 'badge-drift'}`}>
                    {w.is_alive ? '活跃' : '离线'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const [heatmap, setHeatmap] = useState(null)
  const [drift, setDrift] = useState(null)
  const [workers, setWorkers] = useState(null)
  const [streamStats, setStreamStats] = useState(null)
  const [skip, setSkip] = useState(0)
  const [driftedOnly, setDriftedOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const limit = 50

  const loadData = useCallback(async () => {
    try {
      const [hm, dr, wk, ss] = await Promise.all([
        fetchHeatmap(),
        fetchDrift({ skip, limit, driftedOnly }),
        fetchWorkers(),
        fetchStreamStats(),
      ])
      setHeatmap(hm)
      setDrift(dr)
      setWorkers(wk)
      setStreamStats(ss)
    } catch (err) {
      console.error('Dashboard load error:', err)
    } finally {
      setLoading(false)
    }
  }, [skip, driftedOnly])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 10000)
    return () => clearInterval(interval)
  }, [loadData])

  const handlePageChange = (newSkip) => {
    setSkip(Math.max(0, newSkip))
  }

  const handleFilterChange = (value) => {
    setDriftedOnly(value)
    setSkip(0)
  }

  const handleRefresh = async () => {
    setLoading(true)
    try {
      const [hm, dr, wk, ss] = await Promise.all([
        fetchHeatmap(true),
        fetchDrift({ skip, limit, driftedOnly, nocache: true }),
        fetchWorkers(),
        fetchStreamStats(),
      ])
      setHeatmap(hm)
      setDrift(dr)
      setWorkers(wk)
      setStreamStats(ss)
    } catch (err) {
      console.error('Dashboard refresh error:', err)
    } finally {
      setLoading(false)
    }
  }

  if (loading && !heatmap) {
    return <div className="page"><div className="loading">加载中...</div></div>
  }

  return (
    <div className="page dashboard-page">
      <div className="page-header">
        <h2>系统构建看板</h2>
        <button className="btn btn-primary" onClick={handleRefresh}>刷新数据</button>
      </div>

      <section className="dashboard-section">
        <h3>内核配置差异热力图</h3>
        <p className="section-desc">按设备型号和内核版本分组，颜色深浅表示配置漂移比例</p>
        <ConfigHeatmap data={heatmap} />
      </section>

      <section className="dashboard-section">
        <h3>配置漂移检测</h3>
        <p className="section-desc">检测设备当前配置与模板期望配置的不一致情况</p>
        <DriftTable
          data={drift}
          skip={skip}
          limit={limit}
          onPageChange={handlePageChange}
          driftedOnly={driftedOnly}
          onFilterChange={handleFilterChange}
        />
      </section>

      <section className="dashboard-section">
        <h3>分布式Worker状态</h3>
        <p className="section-desc">Redis Streams消费者组和Worker健康状态</p>
        <WorkerStatus workers={workers} streamStats={streamStats} />
      </section>
    </div>
  )
}
