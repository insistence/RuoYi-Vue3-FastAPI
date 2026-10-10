<template>
  <div>
    <el-drawer
      :title="`文件审计 - ${fileName}`"
      :visible.sync="visible"
      size="80%"
      append-to-body
      @closed="detailOpen = false"
    >
      <div class="drawer-content">
        <el-form
          ref="queryForm"
          :model="queryParams"
          size="small"
          :inline="true"
          label-width="68px"
        >
          <el-form-item
            label="操作类型"
            prop="action"
          >
            <el-select
              v-model="queryParams.action"
              placeholder="全部操作"
              clearable
              style="width: 200px"
            >
              <el-option
                label="上传"
                value="upload"
              />
              <el-option
                label="下载"
                value="download"
              />
              <el-option
                label="授权变更"
                value="acl_update"
              />
              <el-option
                label="归属转移"
                value="transfer"
              />
              <el-option
                label="移入回收站"
                value="delete"
              />
              <el-option
                label="恢复"
                value="restore"
              />
              <el-option
                label="永久清理"
                value="purge"
              />
              <el-option
                label="存储对账"
                value="reconcile"
              />
              <el-option
                label="保留延期"
                value="retention_extend"
              />
              <el-option
                label="到期处置"
                value="retention_dispose"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            label="操作结果"
            prop="result"
          >
            <el-select
              v-model="queryParams.result"
              placeholder="全部结果"
              clearable
              style="width: 200px"
            >
              <el-option
                label="已授权"
                value="allowed"
              />
              <el-option
                label="已拒绝"
                value="denied"
              />
              <el-option
                label="已完成"
                value="completed"
              />
              <el-option
                label="失败"
                value="failed"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            label="操作用户"
            prop="actorName"
          >
            <el-input
              v-model="queryParams.actorName"
              placeholder="请输入用户名"
              clearable
              style="width: 200px"
              @keyup.enter.native="handleQuery"
            />
          </el-form-item>
          <el-form-item label="操作时间">
            <el-date-picker
              v-model="dateRange"
              value-format="yyyy-MM-dd HH:mm:ss"
              type="datetimerange"
              range-separator="-"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              style="width: 200px"
            />
          </el-form-item>
          <el-form-item label-width="0">
            <el-button
              type="primary"
              icon="el-icon-search"
              size="mini"
              @click="handleQuery"
              >搜索</el-button
            >
            <el-button
              icon="el-icon-refresh"
              size="mini"
              @click="resetQuery"
              >重置</el-button
            >
          </el-form-item>
        </el-form>
        <el-table
          v-loading="loading"
          :data="auditList"
        >
          <el-table-column
            label="操作"
            align="center"
            prop="action"
            width="105"
          >
            <template slot-scope="scope">
              {{ actionLabel(scope.row.action) }}
            </template>
          </el-table-column>
          <el-table-column
            label="结果"
            align="center"
            prop="result"
            width="100"
          >
            <template slot-scope="scope">
              <el-tag :type="resultTagType(scope.row.result)">
                {{ resultLabel(scope.row.result) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="操作用户"
            align="center"
            prop="actorName"
            width="120"
            :show-overflow-tooltip="true"
          />
          <el-table-column
            label="客户端地址"
            align="center"
            prop="ipAddress"
            width="140"
            :show-overflow-tooltip="true"
          />
          <el-table-column
            label="传输字节"
            align="right"
            prop="bytesSent"
            width="110"
          >
            <template slot-scope="scope">
              {{ scope.row.bytesSent ? formatFileSize(scope.row.bytesSent) : '-' }}
            </template>
          </el-table-column>
          <el-table-column
            label="失败原因"
            align="left"
            prop="errorMessage"
            min-width="140"
            :show-overflow-tooltip="true"
          />
          <el-table-column
            label="访问时间"
            align="center"
            prop="accessTime"
            width="180"
          >
            <template slot-scope="scope">
              {{ parseTime(scope.row.accessTime) }}
            </template>
          </el-table-column>
          <el-table-column
            label="详情"
            align="center"
            width="70"
          >
            <template slot-scope="scope">
              <el-tooltip
                content="查看审计详情"
                placement="top"
              >
                <el-button
                  type="text"
                  icon="el-icon-view"
                  @click="handleDetail(scope.row)"
                />
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
        <pagination
          v-show="total > 0"
          :total="total"
          :page.sync="queryParams.pageNum"
          :limit.sync="queryParams.pageSize"
          @pagination="getList"
        />
        <div class="drawer-footer">
          <el-button @click="visible = false">关 闭</el-button>
        </div>
      </div>
    </el-drawer>

    <el-dialog
      title="审计详情"
      :visible.sync="detailOpen"
      width="720px"
      append-to-body
    >
      <el-descriptions
        :column="2"
        border
      >
        <el-descriptions-item label="操作类型">
          {{ actionLabel(detail.action) }}
        </el-descriptions-item>
        <el-descriptions-item label="操作结果">
          {{ resultLabel(detail.result) }}
        </el-descriptions-item>
        <el-descriptions-item label="操作用户">
          {{ detail.actorName || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="客户端地址">
          {{ detail.ipAddress || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="请求ID">
          {{ detail.requestId || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="链路ID">
          {{ detail.traceId || '-' }}
        </el-descriptions-item>
        <el-descriptions-item
          label="操作时间"
          :span="2"
        >
          {{ parseTime(detail.accessTime) }}
        </el-descriptions-item>
        <el-descriptions-item
          label="用户代理"
          :span="2"
        >
          {{ detail.userAgent || '-' }}
        </el-descriptions-item>
        <el-descriptions-item
          label="失败原因"
          :span="2"
        >
          {{ detail.errorMessage || '-' }}
        </el-descriptions-item>
      </el-descriptions>
      <el-table
        v-if="detailEntries.length"
        :data="detailEntries"
        border
        class="mt20"
      >
        <el-table-column
          label="详情项"
          prop="label"
          width="180"
        />
        <el-table-column
          label="内容"
          prop="value"
          :show-overflow-tooltip="true"
        />
      </el-table>
      <el-empty
        v-else
        description="无操作详情"
        :image-size="60"
      />
      <div
        slot="footer"
        class="dialog-footer"
      >
        <el-button @click="detailOpen = false">关 闭</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { listFileAccessLog } from '@/api/system/file'
import {
  actionLabel,
  formatFileSize,
  parseOperationDetail,
  resultLabel,
  resultTagType,
} from './fileFormatters'

export default {
  name: 'FileAuditDrawer',
  data() {
    return {
      visible: false,
      loading: false,
      fileId: '',
      fileName: '',
      auditList: [],
      total: 0,
      dateRange: [],
      detailOpen: false,
      detail: {},
      queryParams: {
        pageNum: 1,
        pageSize: 10,
        action: undefined,
        result: undefined,
        actorName: undefined,
      },
    }
  },
  computed: {
    detailEntries() {
      return parseOperationDetail(this.detail.operationDetail)
    },
  },
  methods: {
    actionLabel,
    formatFileSize,
    resultLabel,
    resultTagType,
    open(row) {
      this.fileId = row.fileId
      this.fileName = row.originalName
      Object.assign(this.queryParams, {
        pageNum: 1,
        action: undefined,
        result: undefined,
        actorName: undefined,
      })
      this.dateRange = []
      this.visible = true
      this.getList()
    },
    getList() {
      this.loading = true
      listFileAccessLog(this.fileId, this.addDateRange({ ...this.queryParams }, this.dateRange))
        .then((response) => {
          this.auditList = response.rows
          this.total = response.total
        })
        .finally(() => {
          this.loading = false
        })
    },
    handleQuery() {
      this.queryParams.pageNum = 1
      this.getList()
    },
    resetQuery() {
      this.dateRange = []
      this.$refs.queryForm.resetFields()
      this.queryParams.pageNum = 1
      this.getList()
    },
    handleDetail(row) {
      this.detail = row
      this.detailOpen = true
    },
  },
}
</script>

<style scoped>
.drawer-content {
  padding: 0 20px 20px;
}

.drawer-footer {
  padding-top: 20px;
  text-align: right;
}
</style>
