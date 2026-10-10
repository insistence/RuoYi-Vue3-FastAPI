<template>
  <el-drawer
    title="文件保留期限提醒"
    :visible.sync="visible"
    size="70%"
    append-to-body
  >
    <div class="drawer-content">
      <el-alert
        title="到期前可延长保留期限；到期后仅在全部业务引用均已到期时才可移入回收站，处置会解除这些业务引用。"
        type="info"
        :closable="false"
        show-icon
        class="mb8"
      />
      <el-form
        ref="queryForm"
        :model="queryParams"
        size="small"
        :inline="true"
        label-width="68px"
      >
        <el-form-item
          label="文件名称"
          prop="originalName"
        >
          <el-input
            v-model="queryParams.originalName"
            placeholder="请输入原始文件名"
            clearable
            style="width: 200px"
            @keyup.enter.native="handleQuery"
          />
        </el-form-item>
        <el-form-item
          label="提醒类型"
          prop="noticeType"
        >
          <el-select
            v-model="queryParams.noticeType"
            placeholder="请选择提醒类型"
            clearable
            style="width: 200px"
          >
            <el-option
              label="即将到期"
              value="expiring"
            />
            <el-option
              label="已到期"
              value="expired"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          label="提醒状态"
          prop="status"
        >
          <el-select
            v-model="queryParams.status"
            placeholder="请选择提醒状态"
            clearable
            style="width: 200px"
          >
            <el-option
              label="未读"
              value="0"
            />
            <el-option
              label="已读"
              value="1"
            />
          </el-select>
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
      <el-row
        :gutter="10"
        class="mb8"
      >
        <el-col :span="1.5">
          <el-button
            type="primary"
            plain
            size="mini"
            icon="el-icon-refresh"
            :loading="scanning"
            @click="handleScan"
            v-hasPermi="['system:file:edit']"
            >扫描</el-button
          >
        </el-col>
        <el-col :span="1.5">
          <el-button
            type="success"
            plain
            size="mini"
            icon="el-icon-check"
            :disabled="!ids.length"
            @click="handleRead"
            >已读</el-button
          >
        </el-col>
      </el-row>
      <el-table
        v-loading="loading"
        :data="reminderList"
        @selection-change="handleSelectionChange"
      >
        <el-table-column
          type="selection"
          width="50"
          align="center"
          :selectable="selectable"
        />
        <el-table-column
          label="文件名称"
          align="left"
          prop="originalName"
          min-width="180"
          :show-overflow-tooltip="true"
        />
        <el-table-column
          label="所有者"
          align="center"
          prop="ownerName"
          width="120"
          :show-overflow-tooltip="true"
        >
          <template slot-scope="scope">{{ scope.row.ownerName || '-' }}</template>
        </el-table-column>
        <el-table-column
          label="所属部门"
          align="center"
          prop="deptName"
          width="140"
          :show-overflow-tooltip="true"
        >
          <template slot-scope="scope">{{ scope.row.deptName || '-' }}</template>
        </el-table-column>
        <el-table-column
          label="提醒类型"
          align="center"
          prop="noticeType"
          width="110"
        >
          <template slot-scope="scope">
            <el-tag :type="scope.row.noticeType === 'expired' ? 'danger' : 'warning'">
              {{ scope.row.noticeType === 'expired' ? '已到期' : '即将到期' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="到期时间"
          align="center"
          prop="expireTime"
          width="180"
        >
          <template slot-scope="scope">{{ parseTime(scope.row.expireTime) }}</template>
        </el-table-column>
        <el-table-column
          label="状态"
          align="center"
          prop="status"
          width="90"
        >
          <template slot-scope="scope">
            <el-tag :type="scope.row.status === '0' ? 'warning' : 'success'">
              {{ scope.row.status === '0' ? '未读' : '已读' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="业务引用"
          align="center"
          prop="referenceCount"
          width="90"
        />
        <el-table-column
          label="提醒时间"
          align="center"
          prop="createTime"
          width="180"
        >
          <template slot-scope="scope">{{ parseTime(scope.row.createTime) }}</template>
        </el-table-column>
        <el-table-column
          label="读取人"
          align="center"
          prop="readBy"
          width="110"
          :show-overflow-tooltip="true"
        >
          <template slot-scope="scope">{{ scope.row.readBy || '-' }}</template>
        </el-table-column>
        <el-table-column
          label="操作"
          align="center"
          width="100"
          fixed="right"
        >
          <template slot-scope="scope">
            <el-tooltip
              content="延长保留期限"
              placement="top"
            >
              <el-button
                type="text"
                icon="el-icon-time"
                @click="handleExtend(scope.row)"
                v-hasPermi="['system:file:edit']"
              />
            </el-tooltip>
            <el-tooltip
              v-if="isExpired(scope.row)"
              :content="
                scope.row.canDispose ? '移入回收站' : '存在永久或尚未到期的业务引用，暂不可处置'
              "
              placement="top"
            >
              <span>
                <el-button
                  type="text"
                  class="danger-action"
                  icon="el-icon-delete"
                  :disabled="!scope.row.canDispose"
                  @click="handleDispose(scope.row)"
                  v-hasPermi="['system:file:remove']"
                />
              </span>
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
    </div>

    <el-dialog
      title="延长文件保留期限"
      :visible.sync="extendOpen"
      width="520px"
      append-to-body
    >
      <el-form
        ref="extendForm"
        :model="extendForm"
        :rules="extendRules"
        label-width="92px"
      >
        <el-form-item label="文件名称">
          <span>{{ currentRow.originalName }}</span>
        </el-form-item>
        <el-form-item label="原到期时间">
          <span>{{ parseTime(currentRow.expireTime) }}</span>
        </el-form-item>
        <el-form-item
          label="新到期时间"
          prop="expireTime"
        >
          <BusinessDateTimePicker
            v-model="extendForm.expireTime"
            label="新到期时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item
          label="延期原因"
          prop="reason"
        >
          <el-input
            v-model="extendForm.reason"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="请输入延期原因"
          />
        </el-form-item>
      </el-form>
      <div
        slot="footer"
        class="dialog-footer"
      >
        <el-button
          type="primary"
          :loading="submitting"
          @click="submitExtend"
          >确 定</el-button
        >
        <el-button @click="extendOpen = false">取 消</el-button>
      </div>
    </el-dialog>
  </el-drawer>
</template>

<script>
import { toBusinessDateTimeInput, serializeTimeFieldsForSubmit } from '@/utils/time'
import BusinessDateTimePicker from '@/components/BusinessDateTimePicker'
import {
  disposeExpiredFile,
  extendFileRetention,
  listFileRetentionReminder,
  readFileRetentionReminder,
  scanFileRetentionReminder,
} from '@/api/system/file'

export default {
  name: 'FileRetentionReminderDrawer',
  components: { BusinessDateTimePicker },
  data() {
    return {
      visible: false,
      loading: false,
      scanning: false,
      submitting: false,
      extendOpen: false,
      reminderList: [],
      total: 0,
      ids: [],
      currentRow: {},
      extendForm: {
        expireTime: undefined,
        reason: undefined,
      },
      extendRules: {
        expireTime: [{ required: true, message: '新的到期时间不能为空', trigger: 'change' }],
        reason: [{ required: true, message: '延期原因不能为空', trigger: 'blur' }],
      },
      queryParams: {
        pageNum: 1,
        pageSize: 10,
        originalName: undefined,
        noticeType: undefined,
        status: '0',
      },
    }
  },
  methods: {
    open() {
      this.visible = true
      this.queryParams.pageNum = 1
      this.getList()
    },
    getList() {
      this.loading = true
      listFileRetentionReminder(this.queryParams)
        .then((response) => {
          this.reminderList = response.rows
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
      this.$refs.queryForm.resetFields()
      this.queryParams.pageNum = 1
      this.getList()
    },
    handleScan() {
      this.scanning = true
      scanFileRetentionReminder()
        .then((response) => {
          const { expiringCount, expiredCount } = response.data
          this.$modal.msgSuccess(
            `扫描完成，新增即将到期${expiringCount}条、已到期${expiredCount}条提醒`
          )
          this.getList()
          this.$emit('refresh')
        })
        .finally(() => {
          this.scanning = false
        })
    },
    selectable(row) {
      return row.status === '0'
    },
    handleSelectionChange(selection) {
      this.ids = selection.map((item) => item.noticeId)
    },
    handleRead() {
      readFileRetentionReminder(this.ids.join(',')).then(() => {
        this.$modal.msgSuccess('提醒已标记为已读')
        this.getList()
      })
    },
    isExpired(row) {
      return new Date(row.expireTime).getTime() <= Date.now()
    },
    handleExtend(row) {
      this.currentRow = row
      this.extendForm = {
        expireTime: this.defaultExtendTime(row.expireTime),
        reason: undefined,
      }
      this.extendOpen = true
      this.$nextTick(() => this.$refs.extendForm.clearValidate())
    },
    submitExtend() {
      this.$refs.extendForm.validate(async (valid) => {
        if (!valid) return
        const submitData = await serializeTimeFieldsForSubmit(this.extendForm, ['expireTime'])
        if (!submitData) return
        this.submitting = true
        extendFileRetention(this.currentRow.noticeId, submitData)
          .then(() => {
            this.$modal.msgSuccess('文件保留期限已延长')
            this.extendOpen = false
            this.getList()
            this.$emit('refresh')
          })
          .finally(() => {
            this.submitting = false
          })
      })
    },
    handleDispose(row) {
      this.$prompt(
        `处置后“${row.originalName}”将移入回收站，并解除${row.referenceCount || 0}条已到期业务引用。请输入处置原因：`,
        '到期文件处置',
        {
          confirmButtonText: '确定处置',
          cancelButtonText: '取消',
          closeOnClickModal: false,
          inputType: 'textarea',
          inputPlaceholder: '请输入处置原因',
          inputValidator: (value) => {
            const reason = value && value.trim()
            if (!reason) return '处置原因不能为空'
            if (reason.length > 500) return '处置原因不能超过500个字符'
            return true
          },
        }
      )
        .then(({ value }) => {
          disposeExpiredFile(row.noticeId, { reason: value.trim() }).then(() => {
            this.$modal.msgSuccess('到期文件已移入回收站')
            this.getList()
            this.$emit('refresh')
          })
        })
        .catch(() => {})
    },
    defaultExtendTime(expireTime) {
      const baseTime = Math.max(Date.now(), new Date(expireTime).getTime())
      const target = new Date(baseTime + 30 * 24 * 60 * 60 * 1000)
      return toBusinessDateTimeInput(target)
    },
  },
}
</script>

<style scoped>
.drawer-content {
  padding: 0 20px 20px;
}

.danger-action {
  color: #f56c6c;
}
</style>
