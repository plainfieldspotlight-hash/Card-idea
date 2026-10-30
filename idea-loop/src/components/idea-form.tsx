import { Field, Input, Select, Textarea } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";

export type IdeaFormValues = {
  id?: string;
  text?: string;
  sourceTitle?: string;
  sourceType?: string;
  tags?: string;
  useNote?: string;
  goalId?: string | null;
  context?: string | null;
  counterpoint?: string | null;
};

type Option = { id: string; name: string };

export function IdeaForm({
  action,
  values = {},
  goals,
  sources,
  tags,
  submitLabel,
  showDepth = false,
}: {
  action: (formData: FormData) => Promise<void>;
  values?: IdeaFormValues;
  goals: Option[];
  sources: { title: string }[];
  tags: Option[];
  submitLabel: string;
  /** Show the optional context / counterpoint fields (idea detail edit). */
  showDepth?: boolean;
}) {
  return (
    <form action={action} className="space-y-5">
      {values.id ? <input type="hidden" name="id" value={values.id} /> : null}

      <Field label="The idea" hint="one to three sentences" htmlFor="text">
        <Textarea
          id="text"
          name="text"
          required
          autoFocus={!values.id}
          defaultValue={values.text ?? ""}
          placeholder="What do you want to remember to use?"
        />
      </Field>

      <div className="grid grid-cols-[1fr_auto] gap-2">
        <Field label="Source" hint="book, article, podcast, person" htmlFor="sourceTitle">
          <Input
            id="sourceTitle"
            name="sourceTitle"
            list="source-options"
            defaultValue={values.sourceTitle ?? ""}
            placeholder="Where it came from"
            autoComplete="off"
          />
          <datalist id="source-options">
            {sources.map((s) => (
              <option key={s.title} value={s.title} />
            ))}
          </datalist>
        </Field>
        <Field label="Type" htmlFor="sourceType">
          <Select id="sourceType" name="sourceType" defaultValue={values.sourceType ?? "book"}>
            <option value="book">Book</option>
            <option value="article">Article</option>
            <option value="podcast">Podcast</option>
            <option value="person">Person</option>
            <option value="other">Other</option>
          </Select>
        </Field>
      </div>

      <Field label="Tag" hint="comma separated for more than one" htmlFor="tags">
        <Input
          id="tags"
          name="tags"
          list="tag-options"
          defaultValue={values.tags ?? ""}
          placeholder="management, pricing"
          autoComplete="off"
        />
        <datalist id="tag-options">
          {tags.map((t) => (
            <option key={t.id} value={t.name} />
          ))}
        </datalist>
      </Field>

      <Field label="Goal" htmlFor="goalId">
        <Select id="goalId" name="goalId" defaultValue={values.goalId ?? ""}>
          <option value="">No goal</option>
          {goals.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Where I could use this" hint="optional" htmlFor="useNote">
        <Input
          id="useNote"
          name="useNote"
          defaultValue={values.useNote ?? ""}
          placeholder="Next 1:1, Friday planning, the launch email…"
        />
      </Field>

      {showDepth ? (
        <>
          <Field label="Context" hint="optional, the original passage" htmlFor="context">
            <Textarea id="context" name="context" defaultValue={values.context ?? ""} />
          </Field>
          <Field label="Counterpoint" hint="optional" htmlFor="counterpoint">
            <Textarea id="counterpoint" name="counterpoint" defaultValue={values.counterpoint ?? ""} />
          </Field>
        </>
      ) : null}

      <SubmitButton className="w-full">{submitLabel}</SubmitButton>
    </form>
  );
}
