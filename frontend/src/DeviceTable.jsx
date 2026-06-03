export default function DeviceTable({ devices, onDelete }) {
  if (devices.length === 0) {
    return <div className="empty-state">暂无设备数据</div>
  }

  const formatTime = (isoStr) => {
    return new Date(isoStr).toLocaleString('zh-CN')
  }

  return (
    <div className="device-table">
      <table>
        <thead>
          <tr>
            <th>设备ID</th>
            <th>型号</th>
            <th>内核版本</th>
            <th>状态</th>
            <th>最后心跳</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((device) => (
            <tr key={device.id}>
              <td><strong>{device.device_id}</strong></td>
              <td>{device.model}</td>
              <td>{device.kernel_version}</td>
              <td>
                <span className={`status-badge ${device.is_online ? 'online' : 'offline'}`}>
                  {device.is_online ? '在线' : '离线'}
                </span>
              </td>
              <td>{formatTime(device.last_heartbeat)}</td>
              <td>{formatTime(device.created_at)}</td>
              <td>
                <button className="btn-danger" onClick={() => onDelete(device.device_id)}>
                  删除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
