<script setup lang="ts">
import type { CheckboxRootProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { computed, defineOptions } from 'vue'
import { reactiveOmit, useVModel } from '@vueuse/core'
import { Check } from 'lucide-vue-next'
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/lib/utils'

interface ExtraProps {
  class?: HTMLAttributes['class']
  modelValue?: boolean
  checked?: boolean | 'indeterminate'
}

defineOptions({ name: 'UiCheckbox' })

const props = defineProps<CheckboxRootProps & ExtraProps>()
const emits = defineEmits<{
  'update:checked': [value: boolean | 'indeterminate']
  'update:modelValue': [value: boolean]
}>()

const delegatedProps = reactiveOmit(props, 'class', 'modelValue', 'checked')
const forwarded = useForwardPropsEmits(delegatedProps, emits)

const model = useVModel(props, 'modelValue', emits, { passive: true })
const isControlled = computed(() => props.modelValue !== undefined)
const currentChecked = computed(() => (isControlled.value ? !!model.value : (props.checked as any)))

function onUpdateChecked(value: boolean | 'indeterminate') {
  // Always forward original update for consumers using v-model:checked
  emits('update:checked', value as any)
  if (isControlled.value) emits('update:modelValue', Boolean(value))
}

function onClickToggle() {
  if (!isControlled.value) return
  emits('update:modelValue', !props.modelValue)
}
</script>

<template>
  <CheckboxRoot
    data-slot="checkbox"
    v-bind="forwarded"
    :checked="currentChecked as any"
    :class="
      cn(
        'peer border-input data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground data-[state=checked]:border-primary focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive size-4 shrink-0 rounded-[4px] border shadow-xs transition-shadow outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50',
        props.class
      )
    "
    @update:checked="onUpdateChecked"
    @click="onClickToggle"
  >
    <CheckboxIndicator
      data-slot="checkbox-indicator"
      class="flex items-center justify-center text-current transition-none"
    >
      <slot>
        <Check class="size-3.5" />
      </slot>
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
